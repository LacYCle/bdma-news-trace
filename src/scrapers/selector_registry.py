"""Scrapling 多平台 CSS/XPath 选择器注册表

集中管理所有目标平台的选择器，每个平台维护 CSS 主方案 + XPath 回退方案。
网站改版时只需更新此文件，无需修改爬虫逻辑。
"""


class SelectorRegistry:
    """平台选择器注册表"""

    SELECTORS: dict[str, dict[str, dict[str, str]]] = {
        # ========== 微博 ==========
        "weibo": {
            "search_card": {
                "css": ".card-wrap, .m-wrap",
                "xpath": '//div[contains(@class,"card")]',
            },
            "post_text": {
                "css": ".txt::text, .WB_text::text, .detail_wbtext_4CRf9::text",
                "xpath": './/div[contains(@class,"WB_text")]/text()',
            },
            "post_images": {
                "css": ".media img::attr(src), .WB_media_a img::attr(src), .woo-picture-img::attr(src)",
                "xpath": './/img[contains(@class,"media")]/@src',
            },
            "user_name": {
                "css": ".name::text, .head_name_24eEB::text",
                "xpath": './/a[contains(@class,"name")]/text()',
            },
            "repost_count": {
                "css": '.repost-count::text, [class*="woo-box-flex"]:nth-child(2) .woo-like-count::text',
                "xpath": './/span[contains(text(),"转发")]/following-sibling::span/text()',
            },
            "comment_count": {
                "css": '.comment-count::text, [class*="woo-box-flex"]:nth-child(3) .woo-like-count::text',
                "xpath": './/span[contains(text(),"评论")]/following-sibling::span/text()',
            },
            "like_count": {
                "css": '.like-count::text, [class*="woo-box-flex"]:nth-child(4) .woo-like-count::text',
                "xpath": './/span[contains(text(),"赞")]/following-sibling::span/text()',
            },
            "timestamp": {
                "css": '.from a::text, .head_ct_2rVq6 .woo-box-flex .woo-box-flex::text',
                "xpath": './/a[contains(@class,"from")]/text()',
            },
            "repost_item": {
                "css": '.repost-item, .comment-list .item, [class*="Feed"]',
                "xpath": '//div[contains(@class,"repost")]',
            },
            "repost_text": {
                "css": '.repost-text::text, .detail_wbtext_4CRf9::text',
                "xpath": './/div[contains(@class,"text")]//text()',
            },
            "repost_user": {
                "css": '.repost-user::text, .head_name_24eEB::text',
                "xpath": './/a[contains(@class,"name")]/text()',
            },
        },

        # ========== 新浪新闻 ==========
        "sina_news": {
            "article_title": {
                "css": "h1::text, .main-title::text, .article-title::text",
                "xpath": '//h1/text()',
            },
            "article_content": {
                "css": "#article-content p::text, #artibody p::text, .article p::text",
                "xpath": '//div[@id="artibody"]//p/text()',
            },
            "article_images": {
                "css": "#article-content img::attr(src), #artibody img::attr(src), .article img::attr(src)",
                "xpath": '//div[@id="artibody"]//img/@src',
            },
            "publish_time": {
                "css": ".date::text, .pub-time::text, .article-time::text, .time-source::text",
                "xpath": '//span[contains(@class,"date")]/text()',
            },
            "source_name": {
                "css": ".source::text, .origin::text",
                "xpath": '//span[contains(@class,"source")]/text()',
            },
            "news_list_item": {
                "css": ".news-item, .feed-card, .item",
                "xpath": '//div[contains(@class,"item")]',
            },
            "news_list_link": {
                "css": "a::attr(href)",
                "xpath": './/a[1]/@href',
            },
            "news_list_title": {
                "css": "a::text, h2::text, .title::text",
                "xpath": './/a/text()',
            },
        },

        # ========== 网易新闻 ==========
        "netease_news": {
            "article_title": {
                "css": "h1::text, .post_title::text, .article_title::text",
                "xpath": '//h1/text()',
            },
            "article_content": {
                "css": ".post_content p::text, #content p::text, .article-body p::text",
                "xpath": '//div[@class="post_content"]//p/text()',
            },
            "article_images": {
                "css": ".post_content img::attr(src), #content img::attr(src)",
                "xpath": '//div[@class="post_content"]//img/@src',
            },
            "publish_time": {
                "css": ".post_info::text, .article_info::text, .time::text",
                "xpath": '//span[contains(@class,"time")]/text()',
            },
            "source_name": {
                "css": ".post_info .source::text, .article_source::text",
                "xpath": '//span[contains(@class,"source")]/text()',
            },
            "news_list_item": {
                "css": ".news-item, .item, .list-item",
                "xpath": '//div[contains(@class,"item")]',
            },
        },

        # ========== 知乎 ==========
        "zhihu": {
            "answer_item": {
                "css": ".List-item, .AnswerItem",
                "xpath": '//div[contains(@class,"AnswerItem")]',
            },
            "answer_text": {
                "css": ".RichText::text, .CopyrightRichText-richText::text",
                "xpath": './/div[contains(@class,"RichText")]//text()',
            },
            "answer_images": {
                "css": ".RichText img::attr(src), figure img::attr(src)",
                "xpath": './/figure//img/@src',
            },
            "author_name": {
                "css": ".AuthorInfo-name a::text, .UserLink-link::text",
                "xpath": './/a[contains(@class,"UserLink")]/text()',
            },
        },
    }

    @classmethod
    def get(cls, platform: str, element: str) -> dict[str, str]:
        """获取选择器 {css, xpath}"""
        if platform not in cls.SELECTORS:
            raise KeyError(f"Unknown platform: {platform}. Available: {list(cls.SELECTORS.keys())}")
        if element not in cls.SELECTORS[platform]:
            raise KeyError(f"Unknown element '{element}' for '{platform}'. "
                           f"Available: {list(cls.SELECTORS[platform].keys())}")
        return cls.SELECTORS[platform][element]

    @classmethod
    def get_css(cls, platform: str, element: str) -> str:
        return cls.get(platform, element)["css"]

    @classmethod
    def get_xpath(cls, platform: str, element: str) -> str:
        return cls.get(platform, element)["xpath"]

    @classmethod
    def get_sources(cls) -> list[str]:
        return list(cls.SELECTORS.keys())
