#!/usr/bin/env python3
"""D1-only counter additions, installed solely in an isolated counting tree."""
def extend(overlay):
 p='src/descriptor.cpp'
 overlay.function(p,r'CowValue<ModeBinding> coordinate_bound_binding\([\s\S]*?const Matrix &L\) \{','coordinate.bind')
 overlay.replace(p,'            return hit->second.internal;',
   '            {'+overlay.count('coordinate.hit')+'return hit->second.internal;}')
 overlay.before(p,'    CowValue<ModeBinding> internal=physical;','coordinate.miss')
 overlay.replace(p,'binding->a_row_norm[i]=binding->A.row(i).lpNorm<1>();',
   '{'+overlay.count('A.norm.build')+'binding->a_row_norm[i]=binding->A.row(i).lpNorm<1>();}')
 overlay.replace(p,'?binding.a_row_norm[i]:binding.A.row(i).lpNorm<1>();',
   '?('+overlay.count('A.norm.reuse').rstrip(';')+',binding.a_row_norm[i])'
   ':('+overlay.count('A.norm.fallback').rstrip(';')+',binding.A.row(i).lpNorm<1>());')
