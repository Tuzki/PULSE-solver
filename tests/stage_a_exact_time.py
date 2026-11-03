"""Exercise the linked production conversion against a Python integer oracle."""
import random
import subprocess
import sys

rng=random.Random(20261103)
u64=(1<<64)-1;i63=(1<<63)-1
cases=[(0,0,0),(0,0,1),(0,1,0),(0,u64,u64),(i63,u64,u64),
       (1,0,0),(1,1,1),(i63,0,0),(-1,0,0)]
cases.extend((rng.choice([0,1,i63,rng.randrange(i63)]),rng.randrange(1<<64),rng.randrange(1<<64)) for _ in range(3000))
result=subprocess.run([sys.argv[1]],input=''.join(f'{w} {t} {s}\n' for w,t,s in cases),text=True,capture_output=True,check=True)
actual=result.stdout.splitlines()
assert len(actual)==len(cases)
for index,((w,t,s),value) in enumerate(zip(cases,actual)):
    if w<0:expected='UNKNOWN_NEGATIVE'
    else:
        number=((w<<128)+(t<<64)+s)*5**128
        digits=str(number);exponent=-128
        if number==0:exponent=0
        else:
            while digits.endswith('0'):digits=digits[:-1];exponent+=1
        expected=f'{digits}|{exponent}'
    assert value==expected,(index,(w,t,s),value,expected)
print('PASS: production T128 conversion equals integer oracle for 3009 boundary/random cases')
