function bench(name, n, f){ n = Math_round(n * SCALE) + 1; var t=now(); var r=f(n); var ms=now()-t; if(ms==0)ms=1; console.log(name, n, 'in', ms, 'ms =', Math_round(n/ms*1000/1e6*100)/100, 'M/s', 'r='+r); }
function Math_round(x){ return (x+0.5)|0; }
bench('for-loop', 100000000, function(n){ var s=0; for (var i=0;i<n;i++){ } return i; });
bench('for-loop-let-sum', 30000000, function(n){ let s=0; for (let i=0;i<n;i++){ s=s+i|0; } return s; });
function add(a,b){ return a+b; }
bench('calls', 20000000, function(n){ var s=0; for (var i=0;i<n;i++){ s=add(s,1); } return s; });
bench('prop-get', 20000000, function(n){ var o={a:1,b:2,c:3,d:4}; var s=0; for (var i=0;i<n;i++){ s=s+o.c; } return s; });
bench('prop-set', 20000000, function(n){ var o={a:1,b:2,c:3,d:4}; for (var i=0;i<n;i++){ o.d=i; } return o.d; });
bench('method-call', 10000000, function(n){ var o={v:1,m:function(x){return x+this.v;}}; var s=0; for (var i=0;i<n;i++){ s=o.m(s); } return s; });
bench('array-rw', 20000000, function(n){ var a=[1,2,3,4,5,6,7,8]; var s=0; for (var i=0;i<n;i++){ a[i&7]=i; s=s+a[(i+1)&7]|0; } return s; });
bench('alloc-obj', 3000000, function(n){ var o; for (var i=0;i<n;i++){ o={a:i,b:i}; } return o.a; });
bench('alloc-arr', 2000000, function(n){ var o; for (var i=0;i<n;i++){ o=[i,i,i]; } return o[0]; });
bench('closure', 3000000, function(n){ var f; for (var i=0;i<n;i++){ f=function(){return i;}; } return f(); });
bench('str-concat', 3000000, function(n){ var s=''; for (var i=0;i<n;i++){ s+='x'; } return s.length; });
bench('str-index', 10000000, function(n){ var s='hello world'; var c=0; for (var i=0;i<n;i++){ c=c+s.charCodeAt(i&7)|0; } return c; });
bench('double-math', 20000000, function(n){ var x=0.5; for (var i=0;i<n;i++){ x=x*1.0000001+0.1; } return x; });
bench('fib(32)', 1, function(n){ function fib(k){ return k<2?k:fib(k-1)+fib(k-2);} return fib(SCALE < 1 ? 5 : 32); });
bench('class-new', 2000000, function(n){ class P{constructor(x){this.x=x;} get(){return this.x;}} var s=0; for(var i=0;i<n;i++){ s=s+new P(i).get()|0;} return s;});
bench('for-of', 5000000, function(n){ var a=[1,2,3,4,5,6,7,8,9,10]; var s=0; for (var k=0;k<n/10;k++) for (var v of a) s=s+v|0; return s;});
bench('try-catch', 1000000, function(n){ var s=0; for (var i=0;i<n;i++){ try { throw i; } catch(e){ s=s+e|0; } } return s;});
