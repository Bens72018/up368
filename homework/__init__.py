# __init__.py 为初始入口文件,工程代码的入口文件.

# 导入意图库
from airscript.intent import Intent
# 导入控件检索相关
from airscript.node import Selector
from airscript.screen import FindImages, Ocr
from airscript.action import click
from airscript.system import R
import os
import re
import time
from difflib import SequenceMatcher

print("程序启动中...")


# ==================== 打开天学网学生 ====================

def open_tianxue_student():
    """
    打开天学网学生APP:
    1) 优先包名启动
    2) 失败后用桌面图标找图点击兜底
    """
    candidate_packages = [
        "com.up366.mobile",
        "com.up366.student",
        "com.up366.tianxue",
    ]

    def verify_opened():
        # 首页文案会变，使用更宽松的识别关键词
        keywords = ["天学网学生", "天学网", "在线作答", "练习", "生词本", "错题本"]
        for kw in keywords:
            if Selector().text(kw).find():
                return True
        return False

    try:
        print("正在启动天学网学生...")
        for pkg in candidate_packages:
            print(f"尝试包名启动: {pkg}")
            try:
                Intent.run(pkg)
            except Exception as e:
                print(f"包名启动异常: {e}")
                continue

            # 启动后轮询识别，避免等待时间不够
            for wait_round in range(4):
                time.sleep(1)
                if verify_opened():
                    print(f"已进入天学网学生（包名: {pkg}，轮询{wait_round + 1}）")
                    return True

        # 包名方式未命中，尝试桌面图标匹配
        print("包名启动未确认成功，尝试找图点击图标: /img/tianxue_student_icon.png")
        if click_image_template("/img/tianxue_student_icon.png", confidence=0.70, retry=6, interval=1):
            for wait_round in range(5):
                time.sleep(1)
                if verify_opened():
                    print(f"已通过图标点击进入天学网学生（轮询{wait_round + 1}）")
                    return True

        print("未能打开天学网学生，请确认包名或图标模板图")
        return False
    except Exception as e:
        print(f"打开天学网学生发生错误: {e}")
        import traceback
        traceback.print_exc()
        return False


# ==================== 通用识图点击 ====================

def click_image_template(template_rel_path, confidence=0.72, retry=5, interval=1):
    """
    通用识图点击:
    - template_rel_path: 资源相对路径，如 /img/tianxue_target.png
    - confidence: 识别置信度
    - retry: 重试次数
    - interval: 每次重试间隔(秒)
    """
    template_path = R(__file__).res(template_rel_path)
    print(f"准备识图点击: {template_path}")

    for i in range(retry):
        try:
            res = FindImages(template_path).confidence(confidence).find()
        except Exception as e:
            print(f"识图异常(请检查图片路径): {e}")
            return False

        if res:
            center_x = int(res["result"][0])
            center_y = int(res["result"][1])
            conf = res.get("confidence", 0)
            print(
                f"第{i+1}次识图命中，置信度: {conf}，点击坐标: ({center_x}, {center_y})"
            )
            print(f"即将点击坐标: ({center_x}, {center_y})")
            click(center_x, center_y)
            return True

        print(f"第{i+1}次未命中模板图: {template_rel_path}")
        time.sleep(interval)

    print(f"识图点击失败: {template_rel_path}")
    return False


def click_text_candidates(candidates, retry=5, interval=1, offset_x=0, offset_y=0, exact_match_only=False, target_depth=None):
    """
    按文字点击:
    1) 优先从控件树里找完全匹配文本，解析控件坐标后点击中心点
    2) 再从TextView列表里做包含匹配，解析控件坐标后点击中心点
    3) 最后用OCR识别文字并点击坐标
    """
    normalized_candidates = [normalize_answer_text(text) for text in candidates]
    print(
        f"准备文字点击，候选文本: {candidates}，坐标偏移: ({offset_x}, {offset_y})，"
        f"严格匹配: {exact_match_only}，目标深度: {target_depth}"
    )

    def _apply_offset(x, y):
        return int(x + offset_x), int(y + offset_y)

    def _is_text_match(raw_text, norm_text):
        if exact_match_only:
            return any(target and raw_text == target for target in candidates)
        return any(target and target in norm_text for target in normalized_candidates)

    def _read_node_value(node, name):
        if not hasattr(node, name):
            return None
        value = getattr(node, name)
        if callable(value):
            try:
                return value()
            except Exception:
                return None
        return value

    def _get_node_depth(node):
        depth = _read_node_value(node, "depth")
        if depth is None:
            return None
        try:
            return int(depth)
        except Exception:
            return None

    def _is_depth_match(node):
        if target_depth is None:
            return True
        depth = _get_node_depth(node)
        print(f"控件深度检查: 当前深度={depth}, 目标深度={target_depth}")
        return depth == target_depth

    def _extract_control_center(node):
        """
        从控件对象里解析中心坐标，优先用于坐标点击。
        """
        def _read_value(obj, name):
            if not hasattr(obj, name):
                return None
            value = getattr(obj, name)
            if callable(value):
                try:
                    return value()
                except Exception:
                    return None
            return value

        def _as_number(value):
            if isinstance(value, (int, float)):
                return value
            if isinstance(value, str):
                try:
                    return float(value)
                except Exception:
                    return None
            return None

        def _fix_center(x, y, source):
            if x is None or y is None:
                return None
            ix = int(x)
            iy = int(y)
            fixed_x = abs(ix) if ix < 0 else ix
            fixed_y = abs(iy) if iy < 0 else iy
            if fixed_x != ix or fixed_y != iy:
                print(f"坐标出现负数，已修正: {source} ({ix}, {iy}) -> ({fixed_x}, {fixed_y})")
            return fixed_x, fixed_y

        # AScript Node 官方坐标字段: center_x / center_y
        cx = _as_number(_read_value(node, "center_x"))
        cy = _as_number(_read_value(node, "center_y"))
        print(f"控件官方中心字段: center_x={cx}, center_y={cy}")
        if cx is not None and cy is not None:
            return _fix_center(cx, cy, "center_x/center_y")

        # AScript Node 官方位置字段: rect.centerX() / rect.centerY()
        rect = _read_value(node, "rect")
        if rect:
            cx = _as_number(_read_value(rect, "centerX"))
            cy = _as_number(_read_value(rect, "centerY"))
            print(f"控件rect中心字段: centerX={cx}, centerY={cy}, rect={rect}")
            if cx is not None and cy is not None:
                return _fix_center(cx, cy, "rect.centerX/centerY")

        def _center_from_box(box):
            if not box:
                return None

            if isinstance(box, dict):
                if all(k in box for k in ("left", "top", "right", "bottom")):
                    return _fix_center((box["left"] + box["right"]) / 2, (box["top"] + box["bottom"]) / 2, "dict left/top/right/bottom")
                if all(k in box for k in ("x", "y", "w", "h")):
                    return _fix_center(box["x"] + box["w"] / 2, box["y"] + box["h"] / 2, "dict x/y/w/h")
                if all(k in box for k in ("cx", "cy")):
                    return _fix_center(box["cx"], box["cy"], "dict cx/cy")

            if isinstance(box, str):
                nums = re.findall(r"-?\d+(?:\.\d+)?", box)
                if len(nums) >= 4:
                    x1, y1, x2, y2 = map(float, nums[:4])
                    return _fix_center((x1 + x2) / 2, (y1 + y2) / 2, "string box")

            if (
                isinstance(box, (list, tuple))
                and len(box) == 4
                and all(isinstance(v, (int, float)) for v in box)
            ):
                x1, y1, x2, y2 = box
                return _fix_center((x1 + x2) / 2, (y1 + y2) / 2, "list box")

            if isinstance(box, (list, tuple)) and len(box) >= 2:
                points = []
                for p in box:
                    if (
                        isinstance(p, (list, tuple))
                        and len(p) >= 2
                        and isinstance(p[0], (int, float))
                        and isinstance(p[1], (int, float))
                    ):
                        points.append((p[0], p[1]))
                if points:
                    xs = [p[0] for p in points]
                    ys = [p[1] for p in points]
                    return _fix_center((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, "point list box")
            return None

        for name in ["bounds", "bound", "rect", "frame", "box", "position"]:
            if not hasattr(node, name):
                continue
            value = getattr(node, name)
            if callable(value):
                try:
                    value = value()
                except Exception:
                    continue
            center = _center_from_box(value)
            if center:
                return center

        return None

    def _debug_print_control_list(control_list, label):
        print(f"========== {label}: 检测到的全部控件 ==========")
        print(f"控件数量: {len(control_list)}")
        for idx, item in enumerate(control_list, 1):
            try:
                raw_text = (item.text or "").strip()
                node_type = _read_node_value(item, "type")
                depth = _get_node_depth(item)
                center = _extract_control_center(item)
                norm_text = normalize_answer_text(raw_text)
                text_match = _is_text_match(raw_text, norm_text) if norm_text else False
                depth_match = (target_depth is None or depth == target_depth)
                print(
                    f"CTRL[{idx:02d}]: text='{raw_text if raw_text else '(空文本)'}' "
                    f"type={node_type} depth={depth} center={center} "
                    f"text_match={text_match} depth_match={depth_match}"
                )
            except Exception as e:
                print(f"CTRL[{idx:02d}]: 打印控件信息失败: {e}")
        print(f"========== {label}: 控件打印结束 ==========")

    def _debug_print_all_selector_nodes():
        if not (exact_match_only and target_depth is not None):
            return

        for selector_expr, selector in [
            ("Selector()", Selector()),
            ("Selector(1)", Selector(1)),
        ]:
            try:
                control_list = selector.find_all() or []
                _debug_print_control_list(control_list, f"{selector_expr}.find_all()")
            except Exception as e:
                print(f"{selector_expr}.find_all() 打印异常: {e}")

    def _debug_print_single_node(node, label):
        print(f"========== {label}: 单个控件检测值 ==========")
        if not node:
            print("控件对象: None")
            print(f"========== {label}: 单个控件打印结束 ==========")
            return

        try:
            raw_text = (node.text or "").strip()
        except Exception as e:
            raw_text = ""
            print(f"读取控件text失败: {e}")

        depth = _get_node_depth(node)
        center = _extract_control_center(node)
        center_x = _read_node_value(node, "center_x")
        center_y = _read_node_value(node, "center_y")
        rect = _read_node_value(node, "rect")
        norm_text = normalize_answer_text(raw_text)
        text_match = _is_text_match(raw_text, norm_text) if norm_text else False
        depth_match = (target_depth is None or depth == target_depth)
        print(f"text='{raw_text if raw_text else '(空文本)'}'")
        print(f"depth={depth}")
        print(f"center={center}")
        print(f"center_x={center_x}, center_y={center_y}")
        print(f"rect={rect}")
        print(f"text_match={text_match}, depth_match={depth_match}")
        print(f"========== {label}: 单个控件打印结束 ==========")

    for i in range(retry):
        print(f"第{i+1}次文字点击尝试")

        for text in candidates:
            try:
                node = Selector().text(text).find()
                if exact_match_only and target_depth is not None:
                    _debug_print_single_node(node, f"Selector().text('{text}').find()")
                if node:
                    raw_node_text = (node.text or "").strip()
                    norm_node_text = normalize_answer_text(raw_node_text)
                    if not _is_text_match(raw_node_text, norm_node_text):
                        print(
                            f"Selector().text('{text}').find() 返回控件但真实文本不匹配，跳过: "
                            f"raw='{raw_node_text}'"
                        )
                        continue

                    if not _is_depth_match(node):
                        print(f"控件完全匹配文本但深度不匹配，跳过: {text}")
                        continue

                    center = _extract_control_center(node)
                    print(f"控件完全匹配: {text}, center={center}")
                    if center:
                        x, y = _apply_offset(center[0], center[1])
                        if offset_x or offset_y:
                            print(f"点击坐标已应用偏移: 原始{center} -> ({x}, {y})")
                        print(f"即将点击坐标: ({x}, {y})")
                        click(x, y)
                        print(f"控件完全匹配并坐标点击成功: {text} @ ({x}, {y})")
                        return True
                    print(f"控件完全匹配但坐标解析失败: {text}")
            except Exception as e:
                print(f"控件完全匹配异常: {text}, {e}")

        try:
            control_list = Selector().type("TextView").find_all() or []
            if exact_match_only and target_depth is not None:
                scan_sources = []
                for selector_expr, selector in [
                    ("Selector().find_all()", Selector()),
                    ("Selector(1).find_all()", Selector(1)),
                ]:
                    try:
                        source_list = selector.find_all() or []
                        _debug_print_control_list(source_list, selector_expr)
                        scan_sources.append((selector_expr, source_list))
                    except Exception as e:
                        print(f"{selector_expr} 打印/扫描异常: {e}")
                _debug_print_control_list(control_list, "Selector().type('TextView').find_all()")
                scan_sources.append(("Selector().type('TextView').find_all()", control_list))
            else:
                scan_sources = [("Selector().type('TextView').find_all()", control_list)]

            for source_label, source_items in scan_sources:
                print(f"开始扫描控件来源: {source_label}")
                for idx, item in enumerate(source_items, 1):
                    raw_text = (item.text or "").strip()
                    norm_text = normalize_answer_text(raw_text)
                    if not norm_text:
                        continue
                    if not _is_text_match(raw_text, norm_text):
                        continue

                    if not _is_depth_match(item):
                        print(f"{source_label} 文本匹配但深度不匹配，跳过: CTRL[{idx:02d}] {raw_text}")
                        continue

                    center = _extract_control_center(item)
                    print(f"{source_label} 匹配: CTRL[{idx:02d}] {raw_text}, center={center}")
                    if center:
                        x, y = _apply_offset(center[0], center[1])
                        if offset_x or offset_y:
                            print(f"点击坐标已应用偏移: 原始{center} -> ({x}, {y})")
                        print(f"即将点击坐标: ({x}, {y})")
                        click(x, y)
                        print(f"{source_label} 坐标点击成功: CTRL[{idx:02d}] {raw_text} @ ({x}, {y})")
                        return True
                    print(f"{source_label} 匹配但坐标解析失败: CTRL[{idx:02d}] {raw_text}")
        except Exception as e:
            print(f"TextView列表匹配异常: {e}")

        if target_depth is not None:
            print("已指定目标深度，跳过OCR匹配")
            print(f"第{i+1}次未找到符合深度的候选控件，{interval}秒后重试")
            time.sleep(interval)
            continue

        try:
            ocr_list = Ocr().find_all() or []
            for idx, item in enumerate(ocr_list, 1):
                raw_text = (item.text or "").strip()
                norm_text = normalize_answer_text(raw_text)
                if not norm_text:
                    continue
                if _is_text_match(raw_text, norm_text):
                    center = extract_center_from_ocr_item(item)
                    print(f"OCR包含匹配: OCR[{idx:02d}] {raw_text}, center={center}")
                    if center:
                        x, y = _apply_offset(center[0], center[1])
                        if offset_x or offset_y:
                            print(f"点击坐标已应用偏移: 原始{center} -> ({x}, {y})")
                        print(f"即将点击坐标: ({x}, {y})")
                        click(x, y)
                        print(f"OCR文字点击成功: {raw_text} @ ({x}, {y})")
                        return True
        except Exception as e:
            print(f"OCR文字匹配异常: {e}")

        print(f"第{i+1}次未找到候选文本，{interval}秒后重试")
        time.sleep(interval)

    print(f"文字点击失败，候选文本: {candidates}")
    return False


def is_text_visible_by_ocr(candidates):
    normalized_candidates = [normalize_answer_text(text) for text in candidates]
    try:
        ocr_list = Ocr().find_all() or []
    except Exception as e:
        print(f"OCR检查文字是否存在异常: {e}")
        return False

    for idx, item in enumerate(ocr_list, 1):
        raw_text = (item.text or "").strip()
        norm_text = normalize_answer_text(raw_text)
        if not norm_text:
            continue
        if any(target and target in norm_text for target in normalized_candidates):
            print(f"OCR仍检测到目标文字: OCR[{idx:02d}] {raw_text}")
            return True
    return False


def wait_text_disappear_by_ocr(candidates, timeout=8, interval=1):
    print(f"等待文字消失，候选文本: {candidates}")
    start_time = time.time()
    attempt = 0
    while time.time() - start_time <= timeout:
        attempt += 1
        if not is_text_visible_by_ocr(candidates):
            print(f"第{attempt}次检查：目标文字已消失")
            return True
        print(f"第{attempt}次检查：目标文字仍存在，{interval}秒后重试")
        time.sleep(interval)

    print(f"等待文字消失超时，候选文本: {candidates}")
    return False


def click_until_text_disappears(candidates, click_retry=3, check_timeout=3, interval=1, max_clicks=5):
    print(f"开始点击直到文字消失，候选文本: {candidates}")
    for attempt in range(1, max_clicks + 1):
        print(f"第{attempt}轮尝试点击目标文字")
        if not click_text_candidates(candidates, retry=click_retry, interval=interval):
            print(f"第{attempt}轮未能点击目标文字")

        if wait_text_disappear_by_ocr(candidates, timeout=check_timeout, interval=interval):
            print(f"目标文字已消失，点击轮次: {attempt}")
            return True

        print(f"第{attempt}轮点击后目标文字仍存在，准备再次尝试")

    print(f"达到最大点击轮次后目标文字仍未消失，候选文本: {candidates}")
    return False


def click_restart_or_go_do(retry=5, interval=1):
    """
    同时检测“重新开始”和“去做题”入口。
    两者都存在时，优先点击“重新开始”。
    """
    for attempt in range(1, retry + 1):
        print(f"第{attempt}次检测“重新开始/去做题”")

        restart_clicked = click_text_candidates(["重新开始"], retry=1, interval=interval, offset_x=20)
        if restart_clicked:
            print("已点击“重新开始”，优先级高于“去做题”")
            time.sleep(0.2)
            confirm_clicked = click_text_candidates(["确定"], retry=5, interval=1, exact_match_only=True, target_depth=18)
            if not confirm_clicked:
                raise RuntimeError("点击“重新开始”后未能点击文本严格等于“确定”的控件")
            time.sleep(1)
            go_do_after_restart_clicked = click_text_candidates(["去做题"], retry=5, interval=1)
            if not go_do_after_restart_clicked:
                raise RuntimeError("点击“重新开始”和“确定”后未能点击“去做题”")
            print("重新开始确认后已点击“去做题”")
            return "restart"

        go_do_clicked = click_text_candidates(["去做题"], retry=1, interval=interval)
        if go_do_clicked:
            print("已点击“去做题”")
            return "go_do"

        print(f"第{attempt}次未检测到“重新开始/去做题”，{interval}秒后重试")
        time.sleep(interval)

    return None


# ==================== 解析标准答案文件 ====================

ANSWER_FILE_PATH = os.path.join(os.path.dirname(__file__), "answers.txt")


def load_standard_answer_text(answer_file_path=ANSWER_FILE_PATH):
    """
    从本地答案文件读取客制化答案。
    answers.txt 默认被 .gitignore 忽略，避免把个人题组/答案提交出去。
    """
    if not os.path.exists(answer_file_path):
        raise FileNotFoundError(
            f"未找到答案文件: {answer_file_path}，请按模板创建 homework/answers.txt"
        )

    with open(answer_file_path, "r", encoding="utf-8") as f:
        return f.read().strip()


def parse_answers_from_standard_text(full_text):
    """
    从标准答案文本中切片:
    - 答案开始：
    - 1.xxx ... 20.xxx
    - 答案结束
    - 答案题组：xxx
    """
    answers = {i: "" for i in range(1, 21)}
    group_name = ""

    def _clip_answer(text, max_len=28):
        text = (text or "").strip()
        if len(text) <= max_len:
            return text

        clipped = text[:max_len]

        # 若第28个字符落在单词中间(前后都不是空格)，舍去这个半个单词
        if max_len < len(text) and clipped and clipped[-1] != " " and text[max_len] != " ":
            if " " in clipped:
                clipped = clipped.rsplit(" ", 1)[0]
            else:
                clipped = ""

        return clipped.strip()

    normalized = full_text.replace("\r\n", "\n")
    start_match = re.search(r"答案开始[:：]?", normalized)
    end_match = re.search(r"答案结束", normalized)
    group_match = re.search(r"答案题组[:：]\s*([^\n\r]+)", normalized)

    if group_match:
        group_name = group_match.group(1).strip()

    if not start_match or not end_match or end_match.start() <= start_match.end():
        return answers, group_name

    answer_block = normalized[start_match.end():end_match.start()].strip()
    marker_re = re.compile(r"(?<!\d)(1?\d|20)\s*\.\s*")
    markers = list(marker_re.finditer(answer_block))
    if not markers:
        return answers, group_name

    for i, marker in enumerate(markers):
        no = int(marker.group(1))
        if not (1 <= no <= 20):
            continue
        seg_start = marker.end()
        seg_end = markers[i + 1].start() if i + 1 < len(markers) else len(answer_block)
        content = answer_block[seg_start:seg_end]
        content = re.sub(r"\s+", " ", content).strip()
        answers[no] = _clip_answer(content)

    return answers, group_name


def debug_print_answers_from_standard_text():
    try:
        standard_answer_text = load_standard_answer_text()
        answers, group_name = parse_answers_from_standard_text(standard_answer_text)
        print("========== 题组名称变量 ==========")
        print(group_name if group_name else "(未识别到题组名称)")
        print("========== 20题答案字典 ==========")
        print(f"字典长度: {len(answers)}")
        for i in range(1, 21):
            print(f"{i}: {answers[i]}")
        return answers, group_name
    except Exception as e:
        print(f"标准答案解析失败: {e}")
        import traceback
        traceback.print_exc()
        return {i: "" for i in range(1, 21)}, ""


def normalize_answer_text(text):
    """
    统一归一化（答案文本和OCR文本共用）:
    1) 小写 + 去空白标点
    2) 易混字符按等价类映射到同一字符
    """
    text = (text or "").strip().lower()
    text = re.sub(r"[\s\-_:：,.，。;；()\[\]（）\'\"`]+", "", text)

    # OCR易混字符等价类映射（两边都统一成同一个标准字符）
    confusable_map = {
        # 0 / o / 〇
        "0": "o", "o": "o", "〇": "o",
        # i / l / 1 / | / !
        "i": "l", "l": "l", "1": "l", "|": "l", "!": "l",
        # q / g / 9
        "q": "g", "g": "g", "9": "g",
        # b / 8
        "b": "b", "8": "b",
        # s / 5
        "s": "s", "5": "s",
        # z / 2
        "z": "z", "2": "z",
        # h / n（常见误识，轻度容错）
        "h": "n",
        # y / v
        "y": "v", "v": "v",
    }

    text = "".join(confusable_map.get(ch, ch) for ch in text)
    return text


def fuzzy_answer_match(target_norm, norm_text, threshold=0.82):
    """
    OCR模糊匹配:
    - 原有包含关系仍然直接命中
    - OCR轻微漏字/错字时，使用相似度兜底
    """
    if not target_norm or not norm_text:
        return False, 0

    if target_norm in norm_text:
        return True, 1

    ratio = SequenceMatcher(None, target_norm, norm_text).ratio()
    if ratio >= threshold:
        return True, ratio

    # OCR文本可能包含选项序号或额外字符，滑窗比较与答案等长的片段
    if len(norm_text) > len(target_norm):
        best_ratio = 0
        window_len = len(target_norm)
        for start in range(0, len(norm_text) - window_len + 1):
            part = norm_text[start:start + window_len]
            best_ratio = max(best_ratio, SequenceMatcher(None, target_norm, part).ratio())
        return best_ratio >= threshold, best_ratio

    return False, ratio

def extract_center_from_ocr_item(item):
    box = getattr(item, "text_box_position", None)
    if not box:
        return None

    if (
        isinstance(box, (list, tuple))
        and len(box) == 4
        and all(isinstance(v, (int, float)) for v in box)
    ):
        x1, y1, x2, y2 = box
        return int((x1 + x2) / 2), int((y1 + y2) / 2)

    if isinstance(box, (list, tuple)) and len(box) >= 2:
        points = []
        for p in box:
            if (
                isinstance(p, (list, tuple))
                and len(p) >= 2
                and isinstance(p[0], (int, float))
                and isinstance(p[1], (int, float))
            ):
                points.append((p[0], p[1]))
        if points:
            xs = [p[0] for p in points]
            ys = [p[1] for p in points]
            return int((min(xs) + max(xs)) / 2), int((min(ys) + max(ys)) / 2)
    return None


def click_answers_with_ocr_loop(answers):
    """
    1) 对答案做归一化处理
    2) 遍历20个答案
    3) 每题while循环OCR识别，命中后点击进入下一题

    匹配规则:
    - 每轮OCR逐条判断: target_norm in norm_text
    """
    def _extract_center_any(obj):
        """更鲁棒地解析OCR对象坐标中心"""
        def _from_box(box):
            if not box:
                return None

            if isinstance(box, dict):
                if all(k in box for k in ("left", "top", "right", "bottom")):
                    return int((box["left"] + box["right"]) / 2), int((box["top"] + box["bottom"]) / 2)
                if all(k in box for k in ("x", "y", "w", "h")):
                    return int(box["x"] + box["w"] / 2), int(box["y"] + box["h"] / 2)
                if all(k in box for k in ("cx", "cy")):
                    return int(box["cx"]), int(box["cy"])

            if isinstance(box, str):
                nums = re.findall(r"-?\d+(?:\.\d+)?", box)
                if len(nums) >= 4:
                    x1, y1, x2, y2 = map(float, nums[:4])
                    return int((x1 + x2) / 2), int((y1 + y2) / 2)

            if (
                isinstance(box, (list, tuple))
                and len(box) == 4
                and all(isinstance(v, (int, float)) for v in box)
            ):
                x1, y1, x2, y2 = box
                return int((x1 + x2) / 2), int((y1 + y2) / 2)

            if isinstance(box, (list, tuple)) and len(box) >= 2:
                points = []
                for p in box:
                    if (
                        isinstance(p, (list, tuple))
                        and len(p) >= 2
                        and isinstance(p[0], (int, float))
                        and isinstance(p[1], (int, float))
                    ):
                        points.append((p[0], p[1]))
                if points:
                    xs = [p[0] for p in points]
                    ys = [p[1] for p in points]
                    return int((min(xs) + max(xs)) / 2), int((min(ys) + max(ys)) / 2)
            return None

        fields = ["text_box_position", "box", "bounds", "bound", "rect", "frame", "position"]
        for name in fields:
            if not hasattr(obj, name):
                continue
            val = getattr(obj, name)
            if callable(val):
                try:
                    val = val()
                except Exception:
                    continue
            center = _from_box(val)
            if center:
                return center

        for xk, yk in [("x", "y"), ("cx", "cy"), ("center_x", "center_y")]:
            if hasattr(obj, xk) and hasattr(obj, yk):
                xv = getattr(obj, xk)
                yv = getattr(obj, yk)
                if isinstance(xv, (int, float)) and isinstance(yv, (int, float)):
                    return int(xv), int(yv)

        return None

    normalized_answers = {}
    for i in range(1, 21):
        normalized_answers[i] = normalize_answer_text(answers.get(i, ""))

    print("========== 归一化答案 ==========")
    for i in range(1, 21):
        print(f"{i}: {normalized_answers[i]}")

    print("========== 开始20题OCR匹配点击 ==========")
    hint_raw = "听第6段录音"
    hint_norm = normalize_answer_text(hint_raw)
    nuonuo = 0

    for qno in range(1, 21):
        target_norm = normalized_answers[qno]
        if not target_norm:
            print(f"第{qno}题答案为空，跳过")
            continue

        if qno == 1:
            print("第1题点击前等待38秒")
            time.sleep(38)

        print(f"第{qno}题开始，目标归一化答案: {target_norm}")
        attempt = 0
        max_attempt = 30
        while True:
            attempt += 1
            if attempt > max_attempt:
                print(f"第{qno}题超过最大尝试次数({max_attempt})，跳过")
                break
            ocr_list = Ocr().find_all() or []
            print(f"第{qno}题第{attempt}次识别，OCR条数: {len(ocr_list)}")

            normalized_ocr_texts = []
            processed_items = []
            for item in ocr_list:
                raw_text = (item.text or "").strip()
                if not raw_text:
                    continue
                norm_text = normalize_answer_text(raw_text)
                normalized_ocr_texts.append(norm_text)
                processed_items.append((item, raw_text, norm_text))

            print(f"第{qno}题第{attempt}次OCR归一化结果: {normalized_ocr_texts}")

            # 全局规则：nuonuo==0 时，只要OCR识别到提示语就置为1
            if nuonuo == 0:
                hint_found = any((hint_raw in rt) or (hint_norm in nt) for _, rt, nt in processed_items)
                if hint_found:
                    nuonuo = 1
                    print("检测到提示语，nuonuo 由0改为1")

            # 每次选择前：若nuonuo==1，等待45秒并置为2（仅触发一次）
            if nuonuo == 1:
                print("选择前检测到nuonuo=1，等待45秒")
                time.sleep(50)
                nuonuo = 2
                print("nuonuo 已改为2，开始选择答案")

            hit = False
            for idx, (item, raw_text, norm_text) in enumerate(processed_items, 1):
                is_match, match_score = fuzzy_answer_match(target_norm, norm_text)
                print(
                    f"第{qno}题第{attempt}次-字符串{idx}: "
                    f"raw='{raw_text}' norm='{norm_text}' -> match={is_match}, score={match_score:.2f}"
                )

                if not is_match:
                    continue

                center = _extract_center_any(item)
                print(f"第{qno}题命中项中心坐标解析结果: {center}")

                if center:
                    x, y = center
                    print(f"即将点击坐标: ({x}, {y})")
                    click(x, y)
                    print(f"第{qno}题命中并点击: {raw_text} -> {norm_text} @ ({x}, {y})")
                    hit = True
                    break

                # 坐标失败时，仍然尝试一次控件兜底点击
                try:
                    node = Selector().text(raw_text).find()
                    if node:
                        node.click()
                        print(f"第{qno}题命中并控件点击兜底: {raw_text} -> {norm_text}")
                        hit = True
                        break
                    else:
                        print(f"第{qno}题命中但控件兜底未找到: {raw_text}")
                except Exception as e:
                    print(f"第{qno}题命中但控件兜底异常: {e}")

            if hit:
                if qno == 3:
                    print("第3题点击完成后等待15秒")
                    time.sleep(15)

                if qno >= 6:
                    print(f"第{qno}题点击成功后，尝试上划400像素")
                    swiped = False
                    try:
                        from airscript.action import swipe
                        swipe(500, 1600, 500, 800, 300)
                        swiped = True
                    except Exception:
                        pass

                    if not swiped:
                        try:
                            from airscript.action import slide
                            slide(500, 1400, 500, 800, 300)
                            swiped = True
                        except Exception:
                            pass

                    if not swiped:
                        try:
                            from airscript.action import drag
                            drag(500, 1400, 500, 800, 300)
                            swiped = True
                        except Exception:
                            pass

                    if not swiped:
                        print("当前环境不支持 swipe/slide/drag，上划失败")
                time.sleep(1)
                break

            retry_interval = 3 if qno == 6 else 1
            print(f"第{qno}题未命中，{retry_interval}秒后重试")
            time.sleep(retry_interval)
def find_group_name_coordinate_with_scroll(group_name, max_scroll=8):
    """
    在当前页面尝试向上滚动并通过控件文本寻找题组名称控件坐标范围
    """
    if not group_name:
        print("题组名称为空，跳过OCR坐标查找")
        return None

    def _normalize_text(text):
        text = (text or "").strip().lower()
        # 去掉空白和常见分隔符，提升文本匹配容错
        text = re.sub(r"[\s\-_:：,.，。;；()\[\]（）]+", "", text)
        return text

    def _extract_bounds(node):
        """
        兼容不同控件边界字段，返回(x1, y1, x2, y2)
        """
        def _read_value(obj, name):
            if not hasattr(obj, name):
                return None
            value = getattr(obj, name)
            if callable(value):
                try:
                    return value()
                except Exception:
                    return None
            return value

        def _as_number(value):
            if isinstance(value, (int, float)):
                return value
            if isinstance(value, str):
                try:
                    return float(value)
                except Exception:
                    return None
            return None

        rect = _read_value(node, "rect")
        if rect:
            left = _as_number(_read_value(rect, "left"))
            top = _as_number(_read_value(rect, "top"))
            width = _as_number(_read_value(rect, "width"))
            height = _as_number(_read_value(rect, "height"))
            if left is not None and top is not None and width is not None and height is not None:
                return int(left), int(top), int(left + width), int(top + height)

            cx = _as_number(_read_value(rect, "centerX"))
            cy = _as_number(_read_value(rect, "centerY"))
            if cx is not None and cy is not None and width is not None and height is not None:
                return int(cx - width / 2), int(cy - height / 2), int(cx + width / 2), int(cy + height / 2)

        candidates = ["bounds", "bound", "rect", "frame", "box", "position"]
        for name in candidates:
            if not hasattr(node, name):
                continue
            value = getattr(node, name)
            if callable(value):
                try:
                    value = value()
                except Exception:
                    continue

            # 字符串格式: [x1,y1][x2,y2]
            if isinstance(value, str):
                nums = re.findall(r"-?\d+", value)
                if len(nums) >= 4:
                    x1, y1, x2, y2 = map(int, nums[:4])
                    return x1, y1, x2, y2

            # 列表/元组格式: [x1,y1,x2,y2]
            if (
                isinstance(value, (list, tuple))
                and len(value) == 4
                and all(isinstance(v, (int, float)) for v in value)
            ):
                x1, y1, x2, y2 = value
                return int(x1), int(y1), int(x2), int(y2)

            # 点列表格式: [[x1,y1],[x2,y2],...]
            if isinstance(value, (list, tuple)) and len(value) >= 2:
                points = []
                for p in value:
                    if (
                        isinstance(p, (list, tuple))
                        and len(p) >= 2
                        and isinstance(p[0], (int, float))
                        and isinstance(p[1], (int, float))
                    ):
                        points.append((int(p[0]), int(p[1])))
                if points:
                    xs = [p[0] for p in points]
                    ys = [p[1] for p in points]
                    return min(xs), min(ys), max(xs), max(ys)
        return None

    def _click_node(node, fallback_bounds=None):
        """
        优先使用控件自身click，失败再回退到坐标点击
        """
        try:
            node.click()
            return True
        except Exception:
            pass

        if fallback_bounds:
            x1, y1, x2, y2 = fallback_bounds
            cx = int((x1 + x2) / 2)
            cy = int((y1 + y2) / 2)
            print(f"即将点击坐标: ({cx}, {cy})")
            click(cx, cy)
            return True
        return False

    def _find_control_bounds():
        control_list = Selector().type("TextView").find_all() or []
        norm_target = _normalize_text(group_name)
        print(f"题组原文: {group_name}")
        print(f"题组归一化: {norm_target}")
        print(f"本次控件识别条数: {len(control_list)}")
        # print("========== 本次检测出的所有TextView控件 ==========")
        # for idx, item in enumerate(control_list, 1):
        #     try:
        #         txt = (item.text or "").strip()
        #         bounds = _extract_bounds(item)
        #         if bounds:
        #             x1, y1, x2, y2 = bounds
        #             bounds_text = f"({x1}, {y1}) - ({x2}, {y2})"
        #         else:
        #             bounds_text = "(坐标范围无法解析)"
        #         print(f"CTRL[{idx:02d}]: text={txt if txt else '(空文本)'} bounds={bounds_text}")
        #     except Exception as e:
        #         print(f"CTRL[{idx:02d}]: 打印控件信息失败: {e}")
        # print("========== TextView控件打印结束 ==========")

        for hit_idx, item in enumerate(control_list):
            txt = (item.text or "").strip()
            norm_txt = _normalize_text(txt)
            if norm_target and norm_target in norm_txt:
                bounds = _extract_bounds(item)
                print(f"命中题组控件文本: {txt}")
                print(f"命中题组控件边界原始对象: {getattr(item, 'bounds', None)}")
                if bounds:
                    x1, y1, x2, y2 = bounds
                    print(f"命中题组控件坐标范围: ({x1}, {y1}) - ({x2}, {y2})")
                else:
                    print("命中题组控件但坐标范围无法解析")

                target_idx = hit_idx + 3
                if target_idx >= len(control_list):
                    print(
                        f"命中题组控件序号={hit_idx}，但往下第三个控件越界(目标序号={target_idx})"
                    )
                    return None

                target_node = control_list[target_idx]
                target_text = (target_node.text or "").strip()
                target_bounds = _extract_bounds(target_node)
                print(
                    f"目标控件序号={target_idx}，文本={target_text if target_text else '(空文本)'}"
                )
                if target_bounds:
                    tx1, ty1, tx2, ty2 = target_bounds
                    cx = int((tx1 + tx2) / 2)
                    cy = int((ty1 + ty2) / 2)
                    print(f"目标控件坐标范围: ({tx1}, {ty1}) - ({tx2}, {ty2})")
                    print(f"目标控件中心坐标: ({cx}, {cy})")
                else:
                    print("目标控件坐标范围无法解析，尝试直接控件点击")

                if not _click_node(target_node, target_bounds):
                    print("目标控件点击失败")
                    return None

                print("目标控件点击成功")
                return target_bounds, target_text
        return None

    def _scroll_up_once():
        # 固定滑动坐标: (500,1800) -> (500,1100)
        try:
            from airscript.action import swipe
            swipe(500, 1800, 500, 1100, 300)
            return True
        except Exception:
            pass

        try:
            from airscript.action import slide
            slide(500, 1800, 500, 1100, 300)
            return True
        except Exception:
            pass

        try:
            from airscript.action import drag
            drag(500, 1800, 500, 1100, 300)
            return True
        except Exception:
            pass

        print("当前运行环境不支持 swipe/slide/drag，跳过滑动")
        return False

    # 先识别一次，没识别到再滑动；每次滑动后再识别一次
    for i in range(max_scroll + 1):
        if i > 0:
            print(f"第{i}次识别前先滑动...")
            if not _scroll_up_once():
                break
            time.sleep(1)

        found = _find_control_bounds()
        if found:
            bounds, text = found
            group_name_bounds = bounds
            print(
                f"第{i+1}次识别并点击成功，目标控件文本: {text}，目标控件坐标范围变量 group_name_bounds={group_name_bounds}"
            )
            return group_name_bounds

        print(f"第{i+1}次识别未找到题组名称")

    print("滚动查找结束，未找到题组名称控件")
    return None

# ==================== 主程序入口 ====================

try:
    print("========== 开始执行 ==========")
    answers_dict, group_name_var = debug_print_answers_from_standard_text()
    time.sleep(1)
    open_tianxue_student()
    # 天学网内目标按钮模板图放这里: /img/tianxue_target.png
    time.sleep(1)
    start_learning_clicked = click_text_candidates(["开始学习"], retry=5, interval=1)
    if not start_learning_clicked:
        start_learning_clicked = click_image_template("/img/tianxue_target.png", confidence=0.72, retry=5, interval=1)
    if not start_learning_clicked:
        raise RuntimeError("未能点击“开始学习”，停止后续流程")
    time.sleep(1)
    find_group_name_coordinate_with_scroll(group_name_var, max_scroll=15)
    # 复制按钮优先按文字点击，避免部分设备在FindImages(copy.png)时停止
    time.sleep(3)
    time.sleep(0.1)
    if not click_until_text_disappears(["知道了"], click_retry=3, check_timeout=3, interval=1, max_clicks=5):
        raise RuntimeError("多次点击“知道了”后文字仍未消失，停止点击“去做题”")
    time.sleep(1)
    entry_result = click_restart_or_go_do(retry=5, interval=1)
    if not entry_result:
        raise RuntimeError("未能点击“重新开始”或“去做题”，停止后续流程")
    time.sleep(1)
    print("========== 进入答案选择流程 ==========")
    time.sleep(2)
    click_answers_with_ocr_loop(answers_dict)
    print("========== 执行完成 ==========")
except Exception as e:
    print(f"========== 主流程异常停止: {e} ==========")
    import traceback
    traceback.print_exc()
