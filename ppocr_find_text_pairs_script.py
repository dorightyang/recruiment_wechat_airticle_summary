import argparse
from ppocr_tools import find_text_pairs


def find_text_pairs_args(img_path):
    group1 = ("今天", ["昨天", "星期"])
    group2 = ("昨天", ["昨天", "星期"])

    result = find_text_pairs(img_path, group1, group2, threshold=0.9)
    # if result:
    #     print(f"找到的成对文字坐标: {result}")
    # else:
    #     print("未找到成对文字")

    return result


if __name__ == "__main__":
    # 设置命令行参数解析
    parser = argparse.ArgumentParser(description="通过 PaddleOCR 查找成对文字坐标")
    parser.add_argument("-s", "--source", type=str,
                        required=True, help="图像文件路径")

    # 解析命令行参数
    args = parser.parse_args()
    img_path = args.source

    # 调用函数并返回结果
    result = find_text_pairs_args(img_path)

    # 打印结果到标准输出
    if result:
        print(result)
    else:
        print("")
