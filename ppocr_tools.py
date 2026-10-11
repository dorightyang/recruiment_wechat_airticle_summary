
from PIL import Image
from paddleocr import PaddleOCR, draw_ocr


def ppocr_demo(img_path="tmp/page_0025.jpeg"):
    # Paddleocr目前支持的多语言语种可以通过修改lang参数进行切换
    # 例如`ch`, `en`, `fr`, `german`, `korean`, `japan`
    # need to run only once to download and load model into memory
    ocr = PaddleOCR(use_angle_cls=False, lang="ch",
                    use_gpu=False, show_log=False)
    result = ocr.ocr(img_path, cls=False)
    for idx in range(len(result)):
        res = result[idx]
        for line in res:
            print(line)

    # 显示结果
    result = result[0]
    image = Image.open(img_path).convert('RGB')
    boxes = [line[0] for line in result]
    txts = [line[1][0] for line in result]
    scores = [line[1][1] for line in result]
    im_show = draw_ocr(image, boxes, txts, scores,
                       font_path='./fonts/simfang.ttf')
    im_show = Image.fromarray(im_show)
    im_show.save('result.jpg')


def find_text_coordinates(image_path, target_text, ocr_model=None, threshold=0.8):
    """
    在图像中寻找目标文字并返回其坐标。

    :param image_path: str, 图像文件路径
    :param target_text: str, 要查找的目标文字
    :param ocr_model: PaddleOCR 实例，如果为 None 则初始化默认模型
    :param threshold: float, 最小置信度阈值，低于该值的结果会被忽略
    :return: list, 包含目标文字对应的坐标 [[x1, y1], [x2, y2], ...] 或空列表
    """
    # 初始化 OCR 模型（若未提供）
    if ocr_model is None:
        ocr_model = PaddleOCR(use_angle_cls=True, lang="ch",
                              use_gpu=False, show_log=False)

    # 执行 OCR 检测
    result = ocr_model.ocr(image_path, cls=False)

    # 遍历结果寻找目标文字
    for idx in range(len(result)):
        res = result[idx]
        for line in res:
            # 提取文本内容、置信度和坐标
            text = line[1][0]
            confidence = line[1][1]
            coordinates = line[0]

            # 匹配目标文字并满足置信度要求
            if text == target_text and confidence >= threshold:
                return coordinates

    # 如果没有找到，返回空列表
    return []


def test_find_target_text():
    img_path = r"C:\Users\yy\Desktop\Snipaste_2024-11-20_12-51-52.png"
    target = "昨天"
    ocr = PaddleOCR(use_angle_cls=True, lang="ch",
                    use_gpu=False, show_log=False)

    coords = find_text_coordinates(
        img_path, target, ocr_model=ocr, threshold=0.9)
    if coords:
        print(f"找到目标文字 '{target}' 的坐标: {coords}")
    else:
        print(f"未找到目标文字 '{target}'")


def test_find_text_pairs():
    img_path = r"C:\Users\yy\Desktop\Snipaste_2024-11-20_12-52-18.png"
    group1 = ("今天", ["昨天", "星期"])
    group2 = ("昨天", ["昨天", "星期"])
    ocr = PaddleOCR(use_angle_cls=False, lang="ch",
                    use_gpu=False, show_log=False)

    result = find_text_pairs(img_path, group1, group2,
                             ocr_model=ocr, threshold=0.9)
    if result:
        print(f"找到的成对文字坐标: {result}")
    else:
        print("未找到成对文字")


def find_text_pairs(image_path, group1, group2, ocr_model=None, threshold=0.8):
    """
    在图像中寻找成对的目标文字组，如果第一组找到则返回其坐标，未找到则检查第二组。

    :param image_path: str, 图像路径
    :param group1: tuple, 第一组目标文字 (pair1, pair2_options)
    :param group2: tuple, 第二组目标文字 (pair1, pair2_options)
    :param ocr_model: PaddleOCR 实例，如果为 None 则初始化默认模型
    :param threshold: float, 最小置信度阈值，低于该值的结果会被忽略
    :return: str, 两个目标文字的中心点坐标 "x1 y1 x2 y2"，如果没有匹配则返回空字符串
    """
    # 初始化 OCR 模型（若未提供）
    if ocr_model is None:
        ocr_model = PaddleOCR(use_angle_cls=False, lang="ch",
                              use_gpu=False, show_log=False)

    # 执行 OCR 检测
    result = ocr_model.ocr(image_path, cls=False)

    # 存储找到的文字及其坐标
    found_texts = []
    for idx in range(len(result)):
        res = result[idx]
        for line in res:
            # 提取文本内容、置信度和坐标
            text = line[1][0]
            confidence = line[1][1]
            coordinates = line[0]

            # 过滤置信度较低的结果
            if confidence >= threshold:
                # 计算文字的中心点坐标
                x_center = sum([point[0] for point in coordinates]) / 4
                y_center = sum([point[1] for point in coordinates]) / 4
                found_texts.append((text, (x_center, y_center)))

    # 查找目标文字的成对逻辑
    def find_pair(pair1, pair2_options):
        point1 = None
        point2 = None
        for text, coord in found_texts:
            if text == pair1:
                point1 = coord
            elif any(option in text for option in pair2_options):  # 子串匹配逻辑
                point2 = coord
        if point1 and point2:
            return f"{int(point1[0])} {int(point1[1])} {int(point2[0])} {int(point2[1])}"
        return ""

    # 依次检查两组条件
    pair1, pair2_options = group1
    result = find_pair(pair1, pair2_options)
    if result:
        return result

    pair1, pair2_options = group2
    return find_pair(pair1, pair2_options)


# 示例用法
if __name__ == "__main__":
    # test_find_text_pairs()
    ppocr_demo()
