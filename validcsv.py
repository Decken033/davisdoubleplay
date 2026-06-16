import pandas as pd


df = pd.read_csv(
    "adj_close.csv",
    dtype={
        "date":str,
        "stock_id":str,
        "adj_close":float,
    }
)
stock_count = df["stock_id"].nunique()
print("adj_close.csv 中股票数量：", stock_count)

print(df.head())


df_1 = pd.read_excel("data_1.xlsx",sheet_name="roe_ttm",index_col=0)
df_1.index = pd.to_datetime(df_1.index.astype(str), format="%Y%m%d")

stock_count_roe = df_1.shape[1]
print("roe_ttm 中股票数量：", stock_count_roe)

print(df_1.head())
print(df_1.index)

df_2 = pd.read_excel("data_1.xlsx",sheet_name="peg",index_col=0)
df_2.index = pd.to_datetime(df_1.index.astype(str), format="%Y%m%d")

stock_count_roe = df_2.shape[1]
print("peg 中股票数量：", stock_count_roe)

print(df_2.head())
print(df_2.index)
