#include "pulse/netlist.hpp"
#include <algorithm>
#include <cctype>
#include <filesystem>
#include <iomanip>
#include <set>
#include <sstream>
namespace pulse {
namespace {
std::string trim(std::string s) {
  auto a=s.find_first_not_of(" \t\r\n");
  return a==s.npos?"":s.substr(a,s.find_last_not_of(" \t\r\n")-a+1);
}
std::string upper(std::string s) { for(char &c:s)c=char(std::toupper((unsigned char)c));return s; }
[[noreturn]] void bad(const Source&s,const std::string&code,const std::string&why) {throw ParseError(s,code,why);}
std::vector<std::string> words(const std::string&s,const Source&src,char separator=' ') {
  std::vector<std::string> out; std::string part;int depth=0;bool quoted=false;
  for(char c:s) {
    if(c=='"') quoted=!quoted;
    if(!quoted) {if(c=='['||c=='('||c=='{')++depth;if(c==']'||c==')'||c=='}')--depth;}
    if(!quoted&&depth==0&&(separator==' '?std::isspace((unsigned char)c):c==separator)) {
      if(!trim(part).empty()) out.push_back(trim(part));
      part.clear();
    } else part+=c;
    if(depth<0)bad(src,"SOFTWARE_SYNTAX","unbalanced declaration");
  }
  if(depth||quoted)bad(src,"SOFTWARE_SYNTAX","unclosed list or quote");
  if(!trim(part).empty()) out.push_back(trim(part));
  return out;
}
std::string unquote(std::string s) {
  s=trim(s);if(s.size()>=2&&s.front()=='"'&&s.back()=='"')return s.substr(1,s.size()-2);return s;
}
std::vector<std::string> list(std::string s,const Source&src) {
  if(s.size()<2||s.front()!='['||s.back()!=']')bad(src,"SOFTWARE_SYNTAX","expected [...] list");
  auto v=words(s.substr(1,s.size()-2),src,',');for(auto &x:v)x=unquote(x);return v;
}
using Opt=std::map<std::string,std::string>;
Opt options(const std::vector<std::string>&w,const Source&src,const std::set<std::string>&allowed) {
  Opt out;for(size_t i=2;i<w.size();++i) {
    auto eq=w[i].find('=');if(eq==w[i].npos)bad(src,"SOFTWARE_SYNTAX","expected named option");
    auto k=upper(w[i].substr(0,eq)),v=w[i].substr(eq+1);
    if(!allowed.count(k)||!out.emplace(k,v).second)bad(src,"SOFTWARE_OPTION","unknown or duplicate option "+k);
  }return out;
}
std::string get(const Opt&o,const std::string&key,const std::string&fallback="") {
  auto it=o.find(key);return it==o.end()?fallback:unquote(it->second);
}
void identifier(const std::string&s,const Source&src) {
  if(s.empty()||!(std::isalpha((unsigned char)s[0])||s[0]=='_')||
    !std::all_of(s.begin(),s.end(),[](unsigned char c){return std::isalnum(c)||c=='_';}))
    bad(src,"SOFTWARE_IDENTIFIER","invalid identifier "+s);
}
double value(std::string s,const std::map<std::string,double>&p,const Source&src) {
  if(s.size()>1&&s.front()=='{'&&s.back()=='}')s=s.substr(1,s.size()-2);
  try{return fixed_value(s,p);}catch(const std::exception&e){bad(src,"SOFTWARE_PARAMETER",e.what());}
}
std::string number(double d){std::ostringstream s;s<<std::setprecision(17)<<d;return s.str();}
struct Line {std::string text;Source source;};
std::string section_name(std::string s) {
  s=upper(trim(s));
  if(s=="参数域"||s=="PARAMETERS")return "PARAMETERS";
  if(s=="仿真参数配置"||s=="SIMULATION")return "SIMULATION";
  if(s=="电气域连接网表"||s=="ELECTRICAL")return "ELECTRICAL";
  if(s=="虚拟MCU配置域"||s=="MCU")return "MCU";
  if(s=="代码域"||s=="CODE")return "CODE";
  return "";
}
}
Netlist parse_pre_markdown(const std::string &text,const std::string&filename) {
  std::map<std::string,std::vector<Line>> sections;
  std::map<std::string,int> seen;
  std::map<std::string,std::string> inline_code;
  std::istringstream input(text);std::string raw,section,language,current_program;
  bool fence=false,header=false;int line=0,order=0;
  for(;std::getline(input,raw);) {
    ++line;auto t=trim(raw);Source src{filename,section,"",line,1};
    if(t.rfind("```",0)==0) {
      if(fence){fence=false;language.clear();}
      else {
        fence=true;language=upper(trim(t.substr(3)));
        if(language!="PULSE"&&language!="C")bad(src,"SOFTWARE_FENCE","only pulse and c blocks are supported");
        if(language=="C"&&(section!="CODE"||current_program.empty()))bad(src,"INLINE_CODE_OWNER","C block needs a preceding PROGRAM declaration");
        if(language=="C"&&!inline_code.emplace(current_program,"").second)bad(src,"INLINE_CODE_OWNER","one C block per inline program");
      }continue;
    }
    if(fence) {
      if(language=="C")inline_code[current_program]+=raw+"\n";
      else if(!t.empty()&&t[0]!='*') {
        if(section.empty())bad(src,"INVALID_SECTION","pulse block is outside a five-zone section");
        if(t[0]=='+') {
          if(sections[section].empty())bad(src,"INVALID_CONTINUATION","no previous declaration");
          sections[section].back().text+=" "+trim(t.substr(1));
        }else sections[section].push_back({t,src});
        if(section=="CODE") {auto w=words(t,src);if(w.size()>=2&&upper(w[0])=="PROGRAM")current_program=w[1];}
      }continue;
    }
    if(t=="# PULSE Netlist v1.2pre"||t=="# PULSE Netlist v1.2"||t=="# PULSE Netlist v1.20") {
      if(header||order)bad(src,"INVALID_HEADER","duplicate or misplaced header");
      header=true;continue;
    }
    if(t.rfind("## ",0)==0) {
      section=section_name(t.substr(3));
      if(section.empty())bad(src,"INVALID_SECTION","unknown five-zone section");
      int next=section=="PARAMETERS"?1:section=="SIMULATION"?2:section=="ELECTRICAL"?3:section=="MCU"?4:5;
      if(!header||next<=order||++seen[section]>1)bad(src,"INVALID_SECTION_ORDER","five zones must follow the declared order");
      order=next;
    }
  }
  Source end{filename,section,"",line,1};
  if(fence)bad(end,"INVALID_MARKDOWN","unclosed fence");
  if(!header)bad(end,"INVALID_HEADER","missing V1.2pre header");
  for(auto key:{"PARAMETERS","SIMULATION","ELECTRICAL","MCU","CODE"})
    if(seen[key]!=1)bad(end,"MISSING_SECTION",key);
  std::map<std::string,double> params;
  for(auto &l:sections["PARAMETERS"]) {
    auto w=words(l.text,l.source);auto eq=l.text.find('=');
    if(w.empty()||upper(w[0])!=".PARAM"||eq==l.text.npos)bad(l.source,"INVALID_PARAMETER","expected .PARAM name=value");
    auto key=trim(l.text.substr(6,eq-6));identifier(key,l.source);
    if(params.count(key))bad(l.source,"INVALID_PARAMETER","duplicate parameter");
    params[key]=value(l.text.substr(eq+1),params,l.source);
  }
  std::map<std::string,Netlist::Program> programs;
  auto base=std::filesystem::absolute(std::filesystem::path(filename)).parent_path();
  for(auto &l:sections["CODE"]) {
    auto w=words(l.text,l.source);
    if(w.size()<2||upper(w[0])!="PROGRAM")bad(l.source,"SOFTWARE_SYNTAX","code zone expects PROGRAM name");
    identifier(w[1],l.source);auto o=options(w,l.source,{"SOURCES","SOURCE"});
    if(o.count("SOURCE")==o.count("SOURCES"))bad(l.source,"SOFTWARE_SOURCE","choose SOURCE=INLINE or SOURCES=[...]");
    Netlist::Program p;p.name=w[1];p.source=l.source;
#if defined(_WIN32)
    p.binary=(base/".pulse_modules"/(p.name+".dll")).string();
#else
    p.binary=(base/".pulse_modules"/(p.name+".so")).string();
#endif
    if(o.count("SOURCE")) {
      if(upper(get(o,"SOURCE"))!="INLINE"||!inline_code.count(p.name))bad(l.source,"SOFTWARE_SOURCE","inline source is missing");
      p.inline_source=inline_code.at(p.name);
    }else {
      p.sources=list(o.at("SOURCES"),l.source);
      if(p.sources.empty())bad(l.source,"SOFTWARE_SOURCE","source list is empty");
      for(auto &name:p.sources) {
        auto path=std::filesystem::path(name);
        if(path.filename()!=path||path.extension()!=".c")bad(l.source,"SOFTWARE_SOURCE","list same-folder .c file names only");
        if(!std::filesystem::is_regular_file(base/path))bad(l.source,"SOFTWARE_SOURCE","source file missing: "+name);
      }
    }
    if(!programs.emplace(p.name,p).second)bad(l.source,"SOFTWARE_SOURCE","duplicate program "+p.name);
  }
  for(auto &[name,body]:inline_code)if(!programs.count(name)||programs.at(name).inline_source.empty())bad(end,"SOFTWARE_SOURCE","orphan or empty inline source");
  struct Mcu {std::string program,init;};std::map<std::string,Mcu> mcus;
  for(auto &l:sections["MCU"]) {
    auto w=words(l.text,l.source);if(w.size()<2)bad(l.source,"SOFTWARE_SYNTAX","expected type and name");
    identifier(w[1],l.source);
    if(upper(w[0])=="MCU") {
      auto o=options(w,l.source,{"PROGRAM","INIT"});auto p=get(o,"PROGRAM");
      if(!programs.count(p)||!mcus.emplace(w[1],Mcu{p,get(o,"INIT")}).second)bad(l.source,"SOFTWARE_MCU","unknown program or duplicate MCU");
    }
  }
  std::vector<Line> extra;std::vector<Netlist::Task> tasks;std::set<std::string> task_mcus,task_names;
  for(auto &l:sections["MCU"]) {
    auto w=words(l.text,l.source);auto kind=upper(w[0]);
    if(kind=="MCU")continue;
    if(kind=="TIMER") {
      auto o=options(w,l.source,{"MCU","PERIOD","START"});
      if(o.count("MCU")&&!mcus.count(get(o,"MCU")))bad(l.source,"SOFTWARE_MCU","unknown timer MCU");
      double period=value(get(o,"PERIOD"),params,l.source),start=value(get(o,"START","0"),params,l.source);
      extra.push_back({"EVENT_PRE_TIMER_"+w[1]+" "+w[1]+" MODE=PERIODIC PERIOD="+number(period)+" START="+number(start),l.source});continue;
    }
    if(kind!="TASK")bad(l.source,"SOFTWARE_PREVIEW_SCOPE","preview supports MCU, TIMER and TASK; ADC/DAC/PWM peripheral models are not implemented yet");
    auto o=options(w,l.source,{"MCU","TRIGGER","ENTRY","INPUTS","OUTPUTS","INIT_OUTPUTS","PARAMS","START"});
    Netlist::Task task;task.name=w[1];task.source=l.source;task.mcu=get(o,"MCU");
    if(!mcus.count(task.mcu))bad(l.source,"SOFTWARE_MCU","unknown task MCU");
    if(!task_mcus.insert(task.mcu).second)bad(l.source,"SOFTWARE_PREVIEW_SCOPE","one task per MCU is supported in this preview");
    if(!task_names.insert(task.name).second)bad(l.source,"SOFTWARE_TASK","duplicate task");
    task.program=mcus.at(task.mcu).program;task.init=mcus.at(task.mcu).init;
    task.entry=get(o,"ENTRY");identifier(task.entry,l.source);if(!task.init.empty())identifier(task.init,l.source);
    task.trigger=get(o,"TRIGGER");task.self_trigger=upper(task.trigger)=="SELF";
    if(task.self_trigger) {
      task.trigger="PRE_SELF_"+task.name;
      auto start=value(get(o,"START","0"),params,l.source);
      extra.push_back({"EVENT_PRE_SELF_"+task.name+" "+task.trigger+" MODE=AT AT="+number(start),l.source});
    }else if(o.count("START"))bad(l.source,"SOFTWARE_TASK","START applies only to self-triggered tasks");
    if(task.trigger.empty())bad(l.source,"SOFTWARE_TASK","task trigger is required");
    task.wake_trigger=task.self_trigger?task.trigger:"PRE_WAKE_"+task.name;
    if(!task.self_trigger)
      extra.push_back({"EVENT_PRE_WAKE_"+task.name+" "+task.wake_trigger+" MODE=AT AT=0",l.source});
    task.inputs=list(get(o,"INPUTS","[]"),l.source);task.outputs=list(get(o,"OUTPUTS","[]"),l.source);
    for(auto &x:list(get(o,"INIT_OUTPUTS","[]"),l.source))task.initial_outputs.push_back(value(x,params,l.source));
    for(auto &x:list(get(o,"PARAMS","[]"),l.source))task.parameters.push_back(value(x,params,l.source));
    if(task.outputs.size()!=task.initial_outputs.size())bad(l.source,"SOFTWARE_PORTS","INIT_OUTPUTS must match OUTPUTS");
    for(size_t j=0;j<task.outputs.size();++j) {
      const auto port = task.outputs[j].find("::") == std::string::npos ?
                        "REAL::" + task.outputs[j] : task.outputs[j];
      extra.push_back({"REG_PRE_SOFTWARE_"+task.name+"_"+std::to_string(j)+" "+port+" "+port+" "+task.trigger+" IC="+number(task.initial_outputs[j]),l.source});
    }
    tasks.push_back(std::move(task));
  }
  std::ostringstream normalized;std::vector<int> original_lines(1,0);
  auto emit=[&](const std::string&s,int source=0){normalized<<s<<"\n";original_lines.push_back(source);};
  emit("# PULSE Netlist v1.1");emit("## Parameters");emit("```pulse");
  for(auto &l:sections["PARAMETERS"])emit(l.text,l.source.line);
  emit("```");
  emit("## Network");emit("```pulse");
  for(auto &l:sections["ELECTRICAL"])emit(l.text,l.source.line);
  for(auto &l:extra)emit(l.text,l.source.line);
  emit("```");
  emit("## Simulation");emit("```pulse");std::optional<double> atom;
  for(auto &l:sections["SIMULATION"]) {
    auto w=words(l.text,l.source);std::string out;
    for(auto &token:w) {
      if(upper(token).rfind("ATOMIC_TIME=",0)==0) {
        if(atom)bad(l.source,"INVALID_SIMULATION","duplicate ATOMIC_TIME");
        atom=value(token.substr(12),params,l.source);
        if(*atom<=0)bad(l.source,"INVALID_SIMULATION","ATOMIC_TIME must be positive");
      }else {if(!out.empty())out+=' ';out+=token;}
    }emit(out,l.source.line);
  }
  emit("```");emit("## Layout");emit("```json");emit("{}");emit("```");
  auto net=parse_markdown(normalized.str(),filename);
  for(auto &p:net.primitives)if(p.source.line>0&&size_t(p.source.line)<original_lines.size())p.source.line=original_lines[p.source.line];
  net.format="1.2pre";net.filename=filename;net.atomic_time=atom;
  net.programs=std::move(programs);net.tasks=std::move(tasks);
  // Preserve executable declarations, input bindings and embedded source in model identity.
  for(auto &l:sections["MCU"])net.canonical+="MCU_DECL "+l.text+"\n";
  for(auto &l:sections["CODE"])net.canonical+="CODE_DECL "+l.text+"\n";
  for(auto &[name,body]:inline_code)net.canonical+="INLINE "+name+"\n"+body;
  if(atom)net.canonical+="ATOMIC_TIME "+number(*atom)+"\n";
  return net;
}
}
