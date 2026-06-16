import pandas as pd
from iFinDPy import *
from login import login, logout
from config import USERNAME, PASSWORD


def test_interface():
    """测试同花顺接口是否能正常获取ROE TTM数据"""
    print("=" * 50)
    print("开始测试同花顺接口")
    print("=" * 50)

    if not login(USERNAME, PASSWORD):
        print("登录失败，无法继续测试")
        return False

    # 测试单个股票单个日期
    test_stock = "000002.SZ"
    test_date = "20091231"

    print(f"\n测试获取股票 {test_stock} 在 {test_date} 的 ROE TTM 数据...")

    try:
        # 测试不同的参数格式
        # 格式1：三参数（可能有未来函数）
        result1 = THS_BD(test_stock, 'roe_ttm', test_date)
        print(f"  三参数测试:")
        print(f"    errorcode: {result1.errorcode}")
        print(f"    data: {result1.data}")



        result2 = THS_BD(test_stock, 'roe_ttm', f'{test_date},100')
        print(f"\n  带参数测试 (日期,100):")
        print(f"    errorcode: {result2.errorcode}")
        print(f"    data: {result2.data}")

        # 判断哪个成功
        if result2.errorcode == 0 and result2.data is not None:
            print(f"\n  ✓ 带时点参数方式成功（推荐，无未来函数）！")
            logout()
            return True
        elif result1.errorcode == 0 and result1.data is not None:
            print(f"\n  ✓ 三参数方式成功（可能有未来函数风险）！")
            logout()
            return True
        else:
            print(f"\n  ✗ 两种方式都失败")
            logout()
            return False

    except Exception as e:
        print(f"✗ 接口调用出错：{e}")
        logout()
        return False


def get_roe_ttm_data():
    """获取所有股票的ROE TTM数据，支持断点续传"""
    print("=" * 50)
    print("开始获取ROE TTM数据")
    print("=" * 50)

    # 读取股票代码
    df = pd.read_csv(
        "../adj_close.csv",
        dtype={
            "date": str,
            "stock_id": str,
            "adj_close": float,
        }
    )
    stock_list = df["stock_id"].unique().tolist()
    stock_count = len(stock_list)
    print(f"共需获取 {stock_count} 只股票的数据")

    # 读取日期列表
    df_dates = pd.read_excel("../data_1.xlsx", sheet_name="roe_ttm", index_col=0)
    date_list = df_dates.index.astype(str).str.replace('-', '').tolist()
    print(f"共需获取 {len(date_list)} 个日期的数据")
    print(f"日期范围：{date_list[0]} 至 {date_list[-1]}")

    # 检查是否有未完成的数据（断点续传）
    output_file = "../roe_ttm_data.csv"
    temp_file = "../roe_ttm_temp.csv"

    if pd.io.common.file_exists(temp_file):
        print(f"\n发现临时文件，从断点继续...")
        existing_df = pd.read_csv(
            temp_file,
            dtype={
                "date": str,
                "stock_id": str,
                "roe_ttm": float,
            }
        )
        all_data = existing_df.to_dict('records')
        completed_set = set(zip(existing_df['date'], existing_df['stock_id']))
        print(f"已完成 {len(completed_set)} 条记录")
    else:
        all_data = []
        completed_set = set()

    # 登录
    if not login(USERNAME, PASSWORD):
        print("登录失败，无法继续")
        return None

    # 批量获取数据
    total_requests = len(stock_list) * len(date_list)
    completed = len(completed_set)

    print(f"\n开始批量获取，共需 {total_requests} 次请求...\n")

    try:
        for date in date_list:
            print(f"正在获取 {date} 的数据...")

            for stock in stock_list:
                # 跳过已完成的
                if (date, stock) in completed_set:
                    continue

                try:
                    # 使用三参数方式（已验证成功）
                    result = THS_BD(stock, 'roe_ttm', date)

                    if result.errorcode == 0 and result.data is not None:
                        # 提取数据
                        roe_value = result.data['roe_ttm'].iloc[0] if len(result.data) > 0 else None
                        all_data.append({
                            'date': date,
                            'stock_id': stock,
                            'roe_ttm': roe_value
                        })
                    else:
                        all_data.append({
                            'date': date,
                            'stock_id': stock,
                            'roe_ttm': None
                        })

                    completed += 1

                    # 每100条保存一次临时文件
                    if completed % 100 == 0:
                        temp_df = pd.DataFrame(all_data)
                        temp_df.to_csv(temp_file, index=False)
                        print(f"  进度: {completed}/{total_requests} ({completed/total_requests*100:.1f}%) - 已保存临时文件")

                except Exception as e:
                    print(f"  ✗ 获取 {stock} 在 {date} 的数据失败: {e}")
                    all_data.append({
                        'date': date,
                        'stock_id': stock,
                        'roe_ttm': None
                    })
                    completed += 1

    except KeyboardInterrupt:
        print("\n\n用户中断！正在保存临时数据...")
        temp_df = pd.DataFrame(all_data)
        temp_df.to_csv(temp_file, index=False)
        print(f"临时数据已保存到: {temp_file}")
        print("下次运行将从断点继续")
        logout()
        return None

    logout()

    # 转换为 DataFrame
    result_df = pd.DataFrame(all_data)
    print(f"\n✓ 数据获取完成！共 {len(result_df)} 条记录")
    print(f"有效数据: {result_df['roe_ttm'].notna().sum()} 条")
    print(f"缺失数据: {result_df['roe_ttm'].isna().sum()} 条")

    # 保存最终文件
    result_df.to_csv(output_file, index=False)
    print(f"\n数据已保存到: {output_file}")

    # 删除临时文件
    import os
    if os.path.exists(temp_file):
        os.remove(temp_file)
        print("临时文件已清理")

    return result_df


if __name__ == "__main__":
    # 先测试接口
    if test_interface():
        print("\n" + "=" * 50)
        response = input("接口测试成功！是否继续批量获取数据？(y/n): ")
        if response.lower() == 'y':
            get_roe_ttm_data()
    else:
        print("\n接口测试失败，请检查配置和网络连接")