from PIL import Image, ImageDraw, ImageFont
import io
import base64


def draw_points_on_image(image_url, points_data):
    # 打开图像
    with Image.open(image_url) as img:

        # 获取原始图像尺寸
        orig_width, orig_height = img.size

        # 创建一个新的透明图像，高度为原图的1.25倍
        new_height = int(orig_height * 1.1111111)
        new_img = Image.new('RGBA', (orig_width, new_height), (255, 255, 255, 0))
        # 将原图粘贴到新图像的顶部
        draw = ImageDraw.Draw(img)

        # 获取图像尺寸
        width, height = img.size

        # 设置字体，你可能需要更改字体文件的路径
        try:
            font = ImageFont.truetype("a.ttc", 16)
        except IOError:
            font = ImageFont.load_default()

        # 定义颜色列表
        colors = ['#fd2766', '#00FF00', '#0000FF', '#FFFF00', '#FF00FF', '#00FFFF']

        # 在图像上绘制点和文本
        for index, point in enumerate(points_data):
            color = colors[index % len(colors)]
            for x, y in point['coordinates']:
                # 将百分比坐标转换为像素坐标
                pixel_x = int(width * x / 100)
                pixel_y = int(height * y / 100)

                # 绘制点
                draw.ellipse([pixel_x - 10, pixel_y - 10, pixel_x + 10, pixel_y + 10], fill=color)

        # 绘制文本
        text = point.get('alt') or point.get('text', '')

        n_width, n_height = new_img.size
        new_img_draw = ImageDraw.Draw(new_img)
        new_img_draw.ellipse([((n_width - n_width + 55)-20) - 15, n_height-30 - 15, ((n_width - n_width + 55)-20) + 15, n_height-30 + 15], fill=color)
        new_img_draw.text(((n_width - n_width + 55), n_height-38), text, font=font, fill=color)
        new_img.paste(img, (0, 0))
        new_img.save("output.png", format="PNG")


# 使用示例
image_url = "test.jpeg"
points_data = [
    {
        'coordinates': [[44.6, 18.5]],
        'alt': 'Point 1'
    }
]

result = draw_points_on_image(image_url, points_data)
print(result)  # 这将打印一个base64编码的图像数据URL