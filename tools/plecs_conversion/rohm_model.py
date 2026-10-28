"""Flatten ROHM PLECS wires and evaluate numeric parameters without executing model code."""
import ast
import math
import operator
from plecs_text import scalar,subs


def number(expr,env):
    tree=ast.parse(expr.strip().replace('^','**'),mode='eval')
    def visit(n):
        if isinstance(n,ast.Expression):return visit(n.body)
        if isinstance(n,ast.Constant) and isinstance(n.value,(int,float)):return n.value
        if isinstance(n,ast.Name):
            if n.id in env:return env[n.id]
            if n.id in ('pi','inf'):return getattr(math,n.id)
            raise ValueError('Unresolved parameter '+n.id)
        if isinstance(n,ast.Attribute) and isinstance(n.value,ast.Name):return env[n.value.id+'.'+n.attr]
        if isinstance(n,ast.UnaryOp) and isinstance(n.op,(ast.UAdd,ast.USub)):
            return visit(n.operand)*(1 if isinstance(n.op,ast.UAdd) else -1)
        if isinstance(n,ast.BinOp) and type(n.op) in (ast.Add,ast.Sub,ast.Mult,ast.Div,ast.Pow):
            return {ast.Add:operator.add,ast.Sub:operator.sub,ast.Mult:operator.mul,ast.Div:operator.truediv,ast.Pow:operator.pow}[type(n.op)](visit(n.left),visit(n.right))
        if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id in ('sqrt','sin','cos','abs'):
            return (abs if n.func.id=='abs' else getattr(math,n.func.id))(*[visit(a) for a in n.args])
        raise ValueError('Unsupported fixed expression '+expr)
    result=visit(tree)
    if not isinstance(result,(int,float)):raise ValueError('Expected numeric parameter')
    return float(result)


def initial_parameters(text):
    env={};unresolved=[]
    for line in text.splitlines():
        line=line.split('%',1)[0]
        for stmt in line.split(';'):
            if not stmt.strip():continue
            if '=' not in stmt:unresolved.append(stmt.strip());continue
            key,expr=map(str.strip,stmt.split('=',1))
            if expr.startswith("'"):continue # Thermal model strings are copied as source, not executed.
            try:env[key]=number(expr,env)
            except (ValueError,SyntaxError,KeyError,ZeroDivisionError) as exc:unresolved.append(dict(statement=stmt.strip(),error=str(exc)))
    return env,unresolved


class Union:
    def __init__(self):self.parent={}
    def find(self,x):
        if x not in self.parent:self.parent[x]=x
        if self.parent[x]!=x:self.parent[x]=self.find(self.parent[x])
        return self.parent[x]
    def join(self,a,b):
        a,b=self.find(a),self.find(b)
        if a!=b:self.parent[b]=a


class Model:
    def __init__(self,root):
        self.env,self.unresolved=initial_parameters(scalar(root)['InitializationCommands'])
        self.u=Union();self.components={};self.input_terms={};self.output_terms={};self.signal_sources=[]
        self.schematics={};self.parent_of={};self.wire_endpoints=set()
        self.walk(subs(root,'Schematic')[0],'',self.env)
        gotos={}
        for path,c in self.components.items():
            if c['Type']=='Goto':gotos.setdefault(c['params'].get('Tag'),[]).append(path)
        for path,c in self.components.items():
            if c['Type']=='From':
                candidates=gotos.get(c['params'].get('Tag'),[]);scope=self.parent_of[path]
                while True:
                    local=[p for p in candidates if self.parent_of[p]==scope]
                    if local:break
                    if not scope:local=candidates;break
                    scope=scope.rsplit('/',1)[0] if '/' in scope else ''
                if len(local)==1:self.u.join((path,1),(local[0],1))
                elif local:raise ValueError('Ambiguous Goto tag '+path)

    def walk(self,s,parent,env):
        self.schematics[parent]=s
        for block in subs(s,'Component'):
            c=scalar(block);path=(parent+'/' if parent else '')+c['Name'];params={scalar(p)['Variable']:scalar(p).get('Value','') for p in subs(block,'Parameter')}
            c.update(path=path,params=params,env=env,block=block);self.components[path]=c;self.parent_of[path]=parent
            if c['Type'] in ('Port','Input','Output') and parent:
                self.u.join((path,1),(parent,int(number(params['Index'],env))))
            children=subs(block,'Schematic')
            if children:
                local=dict(env)
                for key,expr in params.items():
                    try:local[key]=number(expr,env)
                    except (ValueError,SyntaxError,KeyError,ZeroDivisionError):pass
                for child in children:self.walk(child,path,local)
        def ends(block):
            d=scalar(block);out=[]
            for role in ('Src','Dst'):
                if role+'Component' in d:
                    path=(parent+'/' if parent else '')+d[role+'Component'];term=int(d[role+'Terminal'])
                    out.append((path,term))
            for child in subs(block,'Branch'):out.extend(ends(child))
            return out
        def sigs(block):
            d=scalar(block)
            for role in ('Src','Dst'):
                if role+'Component' in d:
                    path=(parent+'/' if parent else '')+d[role+'Component'];term=int(d[role+'Terminal'])
                    (self.output_terms if role=='Src' else self.input_terms).setdefault(path,set()).add(term)
                    if role=='Src':self.signal_sources.append((path,term))
            for child in subs(block,'Branch'):sigs(child)
        for wire in subs(s,'Connection'):
            d=scalar(wire);items=ends(wire)
            for item in items[1:]:self.u.join(items[0],item)
            if d.get('Type')=='Signal':sigs(wire)
            else:self.wire_endpoints.update(items)

    def num(self,c,key,default=None):return number(c['params'].get(key,str(default)),c['env'])
    def pin(self,path,term):return self.u.find((path,term))
