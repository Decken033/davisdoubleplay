import pandas as pd
import os
from iFinDPy import THS_BD
from bisect import bisect_left
from login import login,logout
from config import USERNAME,PASSWORD

def test_pe_ttm_interface():
    print("测试pe_ttm接口")

    #login测试
    if not login(USERNAME, PASSWORD):
        print("登录失败，无法继续测试")
        return False

    test_stock ="000001.SZ"
    test_date ="20100104"
    print(f"测试股票{test_stock}在{test_date}的pe_ttm的数据")


    try:
        result = THS_BD(test_stock, 'pe_ttm', f'{test_date},100')
        if result.errorcode==0:
            print(result.data)
            logout()
            return True
        else:
            print("查询失败",result.errorcode)
            logout()
            return False

    except Exception as e:
        print("测试接口失败",e)
        logout()
        return False

def get_pettm_data():
    print("获取pe_ttm数据")

    # 从roe_ttm_data.csv读取股票列表和调仓日期
    print("正在读取roe_ttm_data.csv以获取股票列表和调仓日...")
    df_roe = pd.read_csv(
        "../roe_ttm_data.csv",
        dtype={
            "date":str,
            "stock_id":str,
            "roe_ttm":float,
        }
    )
    stock_list = sorted(df_roe["stock_id"].unique().tolist())
    stock_count = len(stock_list)
    print(f"股票数量: {stock_count}")

    # 获取调仓日列表
    rebalance_dates = sorted(df_roe["date"].unique().tolist())
    print(f"调仓日数量: {len(rebalance_dates)}")
    print(f"调仓日期范围: {rebalance_dates[0]} 到 {rebalance_dates[-1]}")

    # 读取adj_close.csv获取所有交易日，用于找到前一交易日
    print("\n正在读取adj_close.csv以确定前一交易日...")
    df_price = pd.read_csv(
        "../adj_close.csv",
        dtype={"date":str, "stock_id":str, "adj_close":float}
    )
    all_trading_days = sorted(df_price["date"].unique().tolist())
    print(f"交易日数量: {len(all_trading_days)}")

    # 对每个调仓日，找到前一交易日
    date_list = []
    for rebalance_date in rebalance_dates:
        # 找到严格早于调仓日的最近交易日
        idx = bisect_left(all_trading_days, rebalance_date)

        if idx == 0:
            print(f"  警告: 调仓日 {rebalance_date} 之前没有交易日，跳过")
            continue

        pe_date = all_trading_days[idx - 1]
        date_list.append(pe_date)

        print(f"  调仓日 {rebalance_date} -> PE_TTM取数日 {pe_date}")

    print(f"\n最终需要获取 {len(date_list)} 个日期的pe_ttm数据")

    output_file = "../pe_ttm_data.csv"
    temp_file = "../pe_ttm_temp.csv"

    if os.path.exists(temp_file):
        print(f"检测到临时文件{temp_file}，将从上次中断的地方继续获取数据")
        df_temp = pd.read_csv(temp_file,dtype={"date":str,"stock_id":str,"pe_ttm":float})


        all_data = df_temp.to_dict("records")
        completed_set = set(zip(df_temp['date'], df_temp['stock_id']))
        print(f"已完成{len(completed_set)}")
    else:
        all_data =[]
        completed_set =set()


    if not login(USERNAME, PASSWORD):
        print("get_pettm_data()登录失败")
        return None

    total_requests = len(stock_list)*len(date_list)
    completed = len(completed_set)
    print(f"总共需要{total_requests}次请求")

    try:
        for date in date_list:
            print("正在获取数据")

            for stock in stock_list:
                if(date,stock) in completed_set: continue

                try:
                    result = THS_BD(stock, 'pe_ttm', f'{date},100')
                    if result.errorcode ==0 and result.data is not None:
                        if len(result.data)>0:
                            pe_value = result.data["pe_ttm"].iloc[0]
                        else:
                            pe_value = None
                        all_data.append({"date":date,"stock_id":stock,"pe_ttm":pe_value})

                    else:
                        all_data.append({"date": date, "stock_id": stock, "pe_ttm": None})
                    completed+=1
                    completed_set.add((date, stock))

                    if completed % 100 ==0:
                        temp_df = pd.DataFrame(all_data,columns=["date","stock_id","pe_ttm"])
                        temp_df.to_csv(temp_file,index=False)
                        print(f"  进度: {completed}/{total_requests} ({completed / total_requests * 100:.1f}%) - 已保存临时文件")
                except Exception as e:
                    print(f"股票{stock}在{date}获取失败：{e}")
                    all_data.append({
                       'date': date,
                       'stock_id': stock,
                        'pe_ttm': None
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
    print(f"有效数据: {result_df['pe_ttm'].notna().sum()} 条")
    print(f"缺失数据: {result_df['pe_ttm'].isna().sum()} 条")

    # 保存最终文件
    result_df.to_csv(output_file, index=False)
    print(f"\n数据已保存到: {output_file}")

    # 删除临时文件

    if os.path.exists(temp_file):
        os.remove(temp_file)
        print("临时文件已清理")

    return result_df

if __name__=="__main__":
    if test_pe_ttm_interface():
        print("\n"+"+"*50)
        response = input("接口测试成功！是否继续批量获取数据？(yes/no): ")
        if response.lower()=="yes":
            get_pettm_data()
    else:
        print("\n接口测试失败，请检查配置和网络连接")