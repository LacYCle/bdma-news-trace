"""公开数据集加载与图像处理管线

支持的数据集:
  - CHEF: 中文突发事件数据集 (Chinese Emergency Events)

图像处理:
  - image_downloader: 异步批量图片下载
  - image_pipeline: 下载 + 特征提取 + DB 存储一站式管线
"""

from .chef import CHEFDataset
from .image_downloader import ImageDownloader, parse_image_urls
from .image_pipeline import run_image_pipeline

__all__ = ["CHEFDataset", "ImageDownloader", "parse_image_urls",
           "run_image_pipeline"]
