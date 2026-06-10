import sys, pandas as pd, scanner
start, end = int(sys.argv[1]), int(sys.argv[2])
uni = scanner.load_universe()
sub = uni[uni.tradable=='Y'].reset_index(drop=True).iloc[start:end]
df = scanner.run_scan(sub, use_nse_fallback=False)
if not df.empty:
    df = df.drop(columns=[c for c in ('_cond','_trendline') if c in df.columns])
    df.to_pickle(f"results/_chunk_{start}_{end}.pkl")
    print(f"chunk {start}:{end} -> {len(df)} rows, score5={int((df['Score']==5).sum())}")
else:
    print(f"chunk {start}:{end} -> EMPTY")
