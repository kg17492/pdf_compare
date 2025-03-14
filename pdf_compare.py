import tkinter.filedialog
import subprocess
import pymupdf
import argparse
import math
from pathlib import Path
import concurrent.futures as con
import multiprocessing
import numpy as np

def exclude_none(value, default = 0):
    return default if value is None else value

def path_area(path: dict) -> bool:
    if path["fill"] is None:
        return 0
    x: list[float] = []
    y: list[float] = []
    for item in path["items"]:
        if item[0] == "re":
            continue
        for point in item[1:]:
            x.append(point.x)
            y.append(point.y)
    return abs(
        sum(
            np.array(
                [
                    x[i] - x[i-1] for i, _ in enumerate(x)
                ]
            ) * np.array(
                [
                    y[i] + y[i-1] for i, _ in enumerate(y)
                ]
            ) / 2
        )
    )

def write(
    new_page: pymupdf.Page,
    shape: pymupdf.Shape,
    page: pymupdf.Page,
    color: tuple[float, float, float],
    args: argparse.Namespace
) -> None:

    paths: list[dict] = page.get_drawings()
    scale: float = max(new_page.rect.height, new_page.rect.width) / max(page.rect.height, page.rect.width)
    page_area: float = page.rect.get_area()
    for path in paths:
        for item in path["items"]:  # these are the draw commands
            if item[0] == "l":  # line
                shape.draw_line(
                    item[1] * page.rotation_matrix * scale,
                    item[2] * page.rotation_matrix * scale,
                )
            elif item[0] == "re":  # rectangle
                shape.draw_rect(
                    item[1] * page.rotation_matrix * scale
                )
            elif item[0] == "qu":  # quad
                shape.draw_quad(
                    item[1] * page.rotation_matrix * scale
                )
            elif item[0] == "c":  # curve
                shape.draw_bezier(
                    item[1] * page.rotation_matrix * scale,
                    item[2] * page.rotation_matrix * scale,
                    item[3] * page.rotation_matrix * scale,
                    item[4] * page.rotation_matrix * scale,
                )
            else:
                raise ValueError("unhandled drawing", item)

        shape.finish(
            fill=None if path["fill"] is None else color,
            color=color,                            # line color
            dashes=path["dashes"],                  # line dashing
            even_odd=path.get("even_odd", True),    # control color of overlaps
            closePath=path["closePath"],            # whether to connect last and first point
            lineJoin=exclude_none(path["lineJoin"]),  # how line joins should look like
            lineCap=max(exclude_none(path["lineCap"], [0])),  # how line ends should look like
            width=exclude_none(path["width"]) * scale,      # line width
            stroke_opacity=0.5,                     # same value for both
            fill_opacity=0.1 if path_area(path) / page_area > 1e-4 else 0.5,                       # opacity parameters
        )
    shape.commit()

    if not args.notext:
        textpage: list[dict] = page.get_text("dict")
        for block in textpage["blocks"]:
            for line in block["lines"]:
                cos: float = (pymupdf.Point(x=line["dir"][0], y=line["dir"][1]) * page.rotation_matrix).unit[0]
                rotate: int = round(math.acos(cos) / math.pi * 2) * 90     # 90度単位の必要あり
                for span in line["spans"]:
                    origin: pymupdf.Point = pymupdf.Point(x=span["origin"][0], y=span["origin"][1]) * page.rotation_matrix * scale
                    shape.insert_text(
                        origin,
                        span["text"],
                        fontsize=span["size"] * scale,
                        fontname="japan",
                        color=color,
                        rotate=rotate,
                        morph=(
                            origin,
                            pymupdf.Matrix(
                                a=(args.width_factor if rotate % 180 == 0 else 1.0),
                                b=0,
                                c=0,
                                d=(1.0 if rotate % 180 == 0 else args.width_factor),
                                e=0,
                                f=0,
                            ),
                        ),
                        stroke_opacity=0.5,
                        fill_opacity=0.5,
                    )
        shape.commit()


def compare_page(idx_args: tuple[int, argparse.Namespace]) -> None:
    idx: int
    args: argparse.Namespace
    idx, args = idx_args
    before_page: pymupdf.Page = pymupdf.open(args.input[0])[idx]
    after_page: pymupdf.Page = pymupdf.open(args.input[1])[idx]
    output_doc: pymupdf.Document = pymupdf.open()
    new_page: pymupdf.Page = output_doc.new_page(
        width   = before_page.rect.width,
        height  = before_page.rect.height,
    )
    shape: pymupdf.Shape = new_page.new_shape()
    write(new_page, shape, before_page, (1, 0, .5), args)
    write(new_page, shape, after_page, (0, 1, .5), args)
    output: Path = Path(args.output)
    output_doc.save(output.with_stem(f"{output.stem}-{idx+1:0>3}"))
    print(idx)


if __name__ == "__main__":
    multiprocessing.freeze_support()
    parser: argparse.ArgumentParser = argparse.ArgumentParser(prog="2つのPDFをそれぞれ赤色と緑色にして重ね合わせたPDFを生成します。")
    parser.add_argument("-i", "--input", type=str, nargs=2, default=None, help="入力する2つのPDFファイルを指定します")
    parser.add_argument("-o", "--output", type=str, help="出力ファイルの名前 複数ページある場合は末尾に数字を付してバラバラに出力されます。")
    parser.add_argument("-w", "--width_factor", type=float, default=0.7, help="文字の幅を調整します")
    parser.add_argument("--notext", action="store_true", help="テキストを表示しない")
    parser.add_argument("--noshow", action="store_true", help="結果PDFを開かない")
    args: argparse.Namespace = parser.parse_args()

    if args.input is None:
        args.input = ["", ""]
        args.input[0] = tkinter.filedialog.askopenfilename(
            initialdir=Path.cwd().absolute(),
            filetypes=[("Before", "*.pdf")],
        )
        args.input[1] = tkinter.filedialog.askopenfilename(
            filetypes=[("After", "*.pdf")],
        )

    if args.output is None:
        args.output = tkinter.filedialog.asksaveasfilename(
            defaultextension="pdf",
            initialfile="PDF比較.pdf",
            filetypes=[("Save As", "*.pdf")],
        )
    if args.input[0] == "" or args.input[1] == "":
        raise Exception("ファイル名が無効です")
    if args.output == "":
        raise Exception("ファイル名が無効です")

    before: pymupdf.Document = pymupdf.open(args.input[0])
    with con.ProcessPoolExecutor() as exe:
        exe.map(
            compare_page,
            [
                (idx, args) for idx, _ in enumerate(before)
            ]
        )

    if not args.noshow:
        command: list[str] = ["explorer", Path(args.output).absolute().parent]
        subprocess.Popen(command)
