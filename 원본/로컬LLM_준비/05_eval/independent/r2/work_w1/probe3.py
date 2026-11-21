from common import *
df, cb = load()
print(df.dtypes.astype(str).value_counts().to_dict())
odd = [c for c in df.columns if str(df[c].dtype) not in ('int64', 'float64')]
print('non int64/float64 columns:', [(c, str(df[c].dtype)) for c in odd])
for e in ['ltcare_visit_yn == 1', 'ltcare_grade in [1, 2]', 'ltcare_bn_yn == 1', 'ltcare_institute_yn == 1', 'ltcare_grade == 3', 'dis_yn.isna()', 'sido not in [1, 4, 9]']:
    m = df.eval(e, engine='python')
    print(e, '->', m.dtype, 'NA n=', int(m.isna().sum()), 'true n=', int(m.fillna(False).sum()))
