import pandas as pd

# ─────────────────────────────────────────────
# 1. 读取数据
# ─────────────────────────────────────────────
df_csv = pd.read_csv(
    "adj_close.csv",
    dtype={"date": str, "stock_id": str, "adj_close": float},
)

df_excel = pd.read_excel("data_1.xlsx", sheet_name="roe_ttm", index_col=0)
df_excel.index = pd.to_datetime(df_excel.index.astype(str), format="%Y%m%d")

# ─────────────────────────────────────────────
# 2. 提取各自的股票代码集合
# ─────────────────────────────────────────────
csv_stocks   = set(df_csv["stock_id"].unique())
excel_stocks = set(df_excel.columns.tolist())

only_csv   = sorted(csv_stocks - excel_stocks)   # 仅CSV有
only_excel = sorted(excel_stocks - csv_stocks)   # 仅Excel有
common     = sorted(csv_stocks & excel_stocks)   # 两者共有

# ─────────────────────────────────────────────
# 3. 校验报告
# ─────────────────────────────────────────────
print("=" * 55)
print("         股票代码校验报告")
print("=" * 55)
print(f"  CSV    股票数量 : {len(csv_stocks):>6,}")
print(f"  Excel  股票数量 : {len(excel_stocks):>6,}")
print(f"  两者共有       : {len(common):>6,}")
print(f"  仅CSV  有      : {len(only_csv):>6,}")
print(f"  仅Excel有      : {len(only_excel):>6,}")
print("=" * 55)

if len(only_csv) > 0:
    print(f"\n⚠️  仅在CSV中存在的股票（前20个）：")
    print(only_csv[:20])

if len(only_excel) > 0:
    print(f"\n⚠️  仅在Excel中存在的股票（前20个）：")
    print(only_excel[:20])

if len(only_csv) == 0 and len(only_excel) == 0:
    print("\n✅  两个文件股票代码完全一致，无差异！")

# ─────────────────────────────────────────────
# 4. 将CSV转为宽表，并按统一顺序对齐列
#    统一顺序：取两者共有 → 排序（字母序）
# ─────────────────────────────────────────────
# CSV去重（如原始数据有重复行，取平均）
df_csv_dedup = df_csv.drop_duplicates(subset=["date", "stock_id"])

# 转宽表
df_csv_wide = df_csv_dedup.pivot(index="date", columns="stock_id", values="adj_close")
df_csv_wide.index = pd.to_datetime(df_csv_wide.index, format="%Y%m%d")
df_csv_wide.index.name = "date"

# 只保留共有股票，统一列顺序
df_csv_aligned   = df_csv_wide[common]
df_excel_aligned = df_excel[common]

print(f"\n📐 对齐后形状（仅共有股票）：")
print(f"  CSV   宽表 : {df_csv_aligned.shape}   （行=日期, 列=股票）")
print(f"  Excel 宽表 : {df_excel_aligned.shape}   （行=日期, 列=股票）")
print(f"\n  列顺序是否一致：{list(df_csv_aligned.columns) == list(df_excel_aligned.columns)}")

# ─────────────────────────────────────────────
# 5. 将对齐后的CSV宽表保存，方便后续使用
#    同时将Excel中仅共有列的版本另存
# ─────────────────────────────────────────────
df_csv_aligned.to_csv("adj_close_wide_aligned.csv")
df_excel_aligned.to_excel("roe_ttm_aligned.xlsx")

print("\n💾 已输出：")
print("  adj_close_wide_aligned.csv  —— CSV转宽表，股票列顺序与Excel一致")
print("  roe_ttm_aligned.xlsx        —— Excel筛选共有股票，列顺序与CSV一致")

# ─────────────────────────────────────────────
# 6. 可选：若需要保留所有股票（用NaN填充缺失）
# ─────────────────────────────────────────────
all_stocks = sorted(csv_stocks | excel_stocks)
df_csv_full   = df_csv_wide.reindex(columns=all_stocks)
df_excel_full = df_excel.reindex(columns=all_stocks)

print(f"\n（可选）若保留全部股票（并集，缺失填NaN）：")
print(f"  CSV   宽表 : {df_csv_full.shape}")
print(f"  Excel 宽表 : {df_excel_full.shape}")

