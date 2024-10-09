import os
import re
import threading
import json
import time
import logging
from random import random
from typing import List, Dict

import xml.etree.ElementTree as ET
import re
from typing import List, Dict
from selenium import webdriver
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.action_chains import ActionChains

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
js_code = """
(function() {
    if (window.__recordedRequests) {
        console.log('Request recording script already injected');
        return;
    }

    console.log('Injecting request recording script');
    window.__recordedRequests = [];
    let originalFetch = window.fetch;
    let originalXHROpen = XMLHttpRequest.prototype.open;
    let originalXHRSend = XMLHttpRequest.prototype.send;

    window.fetch = async function() {
        const start = performance.now();
        const request = arguments[0] instanceof Request ? arguments[0] : new Request(...arguments);
        const url = request.url;
        const method = request.method;
        let requestBody;
        try {
            requestBody = await request.clone().text();
        } catch (e) {
            requestBody = "[Unable to capture request body]";
        }

        console.log(`Intercepted fetch request to ${url}`);

        const response = await originalFetch.apply(this, arguments);
        const duration = performance.now() - start;

        const responseClone = response.clone();
        let responseBody;
        try {
            responseBody = await responseClone.text();
        } catch (e) {
            responseBody = "[Unable to capture response body]";
        }

        window.__recordedRequests.push({
            url: url,
            method: method,
            requestBody: requestBody,
            responseBody: responseBody,
            status: response.status,
            duration: duration
        });

        console.log(`Recorded fetch request to ${url}`);

        return response;
    };

    XMLHttpRequest.prototype.open = function() {
        this._url = arguments[1];
        this._method = arguments[0];
        originalXHROpen.apply(this, arguments);
    };

    XMLHttpRequest.prototype.send = function() {
        const start = performance.now();
        this._requestBody = arguments[0];

        console.log(`Intercepted XHR request to ${this._url}`);

        this.addEventListener('load', function() {
            const duration = performance.now() - start;
            window.__recordedRequests.push({
                url: this._url,
                method: this._method,
                requestBody: this._requestBody,
                responseBody: this.responseText,
                status: this.status,
                duration: duration
            });

            console.log(`Recorded XHR request to ${this._url}`);
        });

        originalXHRSend.apply(this, arguments);
    };

    console.log('Request recording script injection complete');
    return 'Injection successful';
})();
"""


class MolmoWrapper:
    def __init__(self, cookie_file_path):
        self.base_url = "https://molmo.allenai.org"
        self.cookies = self.load_cookies(cookie_file_path)
        self.network_requests = []
        self.driver = None
        self.stop_event = threading.Event()

        chrome_options = self.setup_chrome_options()
        self.initialize_driver(chrome_options)

    def setup_chrome_options(self):
        chrome_options = Options()
        chrome_options.add_experimental_option('excludeSwitches', ['enable-automation'])
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--remote-debugging-port=9222")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--log-level=3")
        chrome_options.add_argument("--verbose")
        chrome_options.add_argument("--headless")
        chrome_options.add_argument(
            'user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_13_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/68.0.3440.106 Safari/537.36')
        return chrome_options

    def initialize_driver(self, chrome_options):
        try:
            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=chrome_options)
            self.driver.get(self.base_url)
            for cookie in self.cookies:
                self.add_cookie(cookie)
        except Exception as e:
            logging.error(f"Failed to initialize WebDriver: {e}")
            raise

    def load_cookies(self, file_path):
        try:
            with open(file_path, 'r') as file:
                return json.load(file)
        except json.JSONDecodeError:
            logging.error(f"Error: The file {file_path} does not contain valid JSON.")
            return []
        except FileNotFoundError:
            logging.error(f"Error: The file {file_path} was not found.")
            return []

    def add_cookie(self, cookie):
        cookie.pop('sameSite', None)
        cookie.pop('expires', None)
        cookie.pop('hostOnly', None)

        if cookie['name'].startswith('__Host-'):
            cookie.pop('domain', None)
        elif 'domain' not in cookie:
            logging.warning(f"Warning: 'domain' not specified for cookie: {cookie}")

        if 'name' not in cookie or 'value' not in cookie:
            logging.error(f"Error: Cookie must have 'name' and 'value' attributes: {cookie}")
            return

        current_url = self.driver.current_url
        if not current_url.startswith('https://'):
            logging.warning("Warning: Current URL is not HTTPS. Attempting to switch to HTTPS.")
            https_url = 'https://' + current_url.split('://', 1)[1]
            self.driver.get(https_url)

        try:
            self.driver.add_cookie(cookie)
            logging.info(f"Successfully added cookie: {cookie['name']}")
        except WebDriverException as e:
            logging.error(f"WebDriverException adding cookie: {e}")
        except Exception as e:
            logging.error(f"Unexpected error adding cookie: {e}")

    def create_new_chat(self):
        try:
            self.driver.get(f"{self.base_url}/new")

            # 注入 JavaScript 代码并检查返回值
            print("Injecting JavaScript code")
            injection_result = self.driver.execute_script(js_code)
            print(f"Injection result: {injection_result}")

            # 检查是否成功设置了 window.__recordedRequests
            check_script = """
                          if (window.__recordedRequests) {
                              return 'window.__recordedRequests is set';
                          } else {
                              return 'window.__recordedRequests is not set';
                          }
                          """
            check_result = self.driver.execute_script(check_script)
            print(f"Check result: {check_result}")

            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            current_url = self.driver.current_url
            logging.info(f"New chat created at: {current_url}")
            return current_url
        except Exception as e:
            logging.error(f"Error creating new chat: {e}")
            return None

    def wait_and_click(self, locator, timeout=10):
        try:
            element = WebDriverWait(self.driver, timeout).until(
                EC.element_to_be_clickable(locator)
            )
            ActionChains(self.driver).move_to_element(element).click().perform()
            return True
        except (TimeoutException, NoSuchElementException) as e:
            logging.error(f"Element not found or not clickable: {locator}. Error: {e}")
            return False

    def handle_popup(self, button_text):
        try:
            checkbox_locator = (By.XPATH, "//button[@role='checkbox']")
            if self.wait_and_click(checkbox_locator):
                logging.info("Checkbox clicked")
            else:
                logging.info("Checkbox not found, continuing...")

            time.sleep(1)
            button_locators = [
                (By.XPATH, f"//div[@role='dialog']//button[contains(., '{button_text}')]"),
                (By.XPATH, f"//button[contains(., '{button_text}')]"),
            ]

            for locator in button_locators:
                if self.wait_and_click(locator):
                    logging.info(f"Button '{button_text}' clicked")
                    return

            logging.warning(f"Button '{button_text}' not found, continuing...")
        except Exception as e:
            logging.error(f"Error handling popup: {e}")

    def upload_image(self, image_path):
        abs_image_path = os.path.abspath(image_path)
        try:
            upload_div_xpath = "/html/body/div/main/div/div/div[3]/div/div[2]"
            upload_div = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, upload_div_xpath))
            )
            ActionChains(self.driver).move_to_element(upload_div).click().perform()

            file_input = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='file']"))
            )
            file_input.send_keys(abs_image_path)

            logging.info(f"Image uploaded: {abs_image_path}")

            self.handle_popup("Next")

            self.handle_popup("Let")

        except Exception as e:
            logging.error(f"Error uploading image: {e}")

    def wait_for_button_enabled(self, xpath, timeout=60):
        try:
            WebDriverWait(self.driver, timeout).until_not(
                EC.presence_of_element_located((By.XPATH, f"{xpath}[@disabled]"))
            )
            return True
        except TimeoutException:
            logging.warning(f"Button did not become enabled within {timeout} seconds")
            return False

    def input_and_send_question(self, question):
        try:
            textarea_xpath = "//textarea[@tabindex='0']"
            textarea = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.XPATH, textarea_xpath))
            )

            actions = ActionChains(self.driver)
            actions.move_to_element(textarea).click().send_keys(question).perform()
            logging.info(f"Question inputted: {question}")

            send_button_xpath = "//div[@data-state='closed']//button"
            if self.wait_for_button_enabled(send_button_xpath):
                send_button = WebDriverWait(self.driver, 25).until(
                    EC.element_to_be_clickable((By.XPATH, send_button_xpath))
                )
                actions.move_to_element(send_button).click().perform()
                logging.info("Question sent")
                time.sleep(1)
            else:
                logging.error("Failed to send question: Send button did not become enabled")
        except Exception as e:
            logging.error(f"Error inputting or sending question: {e}")

    def inject_response_listener(self):
        script = """
        // 存储原始引用
        var originalFetch = window.fetch;
        var originalXHROpen = XMLHttpRequest.prototype.open;
        var originalXHRSend = XMLHttpRequest.prototype.send;

        // 初始化存储响应和请求的对象和数组
        window.collectedResponses = window.collectedResponses || {};
        window.collectedRequests = window.collectedRequests || [];

        // 覆盖 fetch 方法来监听响应和拦截请求
        window.fetch = function() {
            var requestTime = new Date().toISOString();
            var requestUrl = arguments[0];
            var requestOptions = arguments[1] || {};
            var requestBody = requestOptions.body || null;

            window.collectedRequests.push({
                time: requestTime,
                url: requestUrl,
                method: requestOptions.method || 'GET',
                body: requestBody
            });

            var fetchCall = originalFetch.apply(this, arguments);
            fetchCall.then(function(response) {
                var clonedResponse = response.clone();
                clonedResponse.text().then(function(body) {
                    window.collectedResponses[response.url] = body;
                });
            });
            return fetchCall;
        };

        // 覆盖 XMLHttpRequest 的 open 方法来拦截请求
        XMLHttpRequest.prototype.open = function() {
            this.requestUrl = arguments[1];
            this.requestMethod = arguments[0];
            originalXHROpen.apply(this, arguments);
        };

        // 覆盖 XMLHttpRequest 的 send 方法来监听响应和记录请求时间和body
        XMLHttpRequest.prototype.send = function(body) {
            var requestTime = new Date().toISOString();
            window.collectedRequests.push({
                time: requestTime,
                url: this.requestUrl,
                method: this.requestMethod,
                body: body
            });

            this.addEventListener('load', function() {
                if (this.status >= 200 && this.status < 300) {
                    window.collectedResponses[this.responseURL] = this.responseText;
                }
            });
            originalXHRSend.apply(this, arguments);
        };
        """
        try:
            self.driver.execute_script(script)
            logging.info("Response listener injected successfully")
        except Exception as e:
            logging.error(f"Failed to inject response listener: {e}")

    def get_requests(self):
        try:
            requests = self.driver.execute_script("""
                var requests = window.collectedRequests || [];
                if (requests.length === 0) {
                    return [];
                }

                var uniqueRequests = [];
                var seenUrls = new Set();

                requests.sort((a, b) => new Date(a.time) - new Date(b.time));

                for (var request of requests) {
                    if (!seenUrls.has(request.url)) {
                        uniqueRequests.push(request);
                        seenUrls.add(request.url);
                    }
                }

                return uniqueRequests;
            """)
            return requests
        except Exception as e:
            logging.error(f"Error getting requests: {e}")
            return []

    def close(self):
        if self.driver:
            self.driver.quit()
            logging.info("Browser closed")
        self.stop_event.set()


def extract_data(data_json):
    extracted_data = {
        "model": None,
        "title": None,
        "contents": []
    }

    for item in data_json:
        extracted_data["title"] = item.get("title")
        message_tree = item.get("messageTree", {})
        roots = message_tree.get("roots", [])
        if roots:
            extracted_data["model"] = roots[0].get("model")
            for root in roots:
                children = root.get("children", [])
                for child in children:
                    if child.get("role") == "assistant":
                        child_content = child.get("content")
                        if child_content:
                            extracted_data["contents"].append(child_content)
        else:
            logging.warning("No roots found in this JSON.")

    return extracted_data


def molmo_remote_process_image(question, image):
    cookie_file_path = 'cookie_file.json'
    molmo = None
    try:
        molmo = MolmoWrapper(cookie_file_path)
        chat_url = molmo.create_new_chat()
        if not chat_url:
            raise Exception("Failed to create new chat")

        molmo.upload_image(image)
        molmo.inject_response_listener()
        molmo.input_and_send_question(question)


        retry_count = 0
        while True:
            requests_list = molmo.get_requests()
            if not requests_list:
                logging.info("No new requests found. Waiting...")
                time.sleep(1)
                retry_count += 1
                continue

            for request_data in requests_list:
                body = request_data.get('body', 'No body found')
                if not body or "messageTree" not in json.dumps(body):
                    continue

                try:
                    data_json = json.loads(body) if isinstance(body, str) else body
                except json.JSONDecodeError:
                    continue

                if not isinstance(data_json, list):
                    continue

                extracted_data = extract_data(data_json)
                if extracted_data["model"] == "Molmo 7B-D" and extracted_data["title"] and extracted_data["contents"]:
                    logging.info("Extracted Data: %s", extracted_data)
                    wait_time = 3
                    print(f"Waiting for {wait_time} seconds to capture requests")
                    # 获取捕获的请求
                    # 获取捕获的请求
                    print("Retrieving captured requests")
                    recorded_requests = molmo.driver.execute_script("return window.__recordedRequests;")

                    if recorded_requests is None:
                        print("Error: window.__recordedRequests is None")
                        # 尝试重新注入脚本
                        print("Attempting to re-inject the script")
                        molmo.driver.execute_script(js_code)
                        time.sleep(15)
                        recorded_requests = molmo.driver.execute_script("return window.__recordedRequests;")
                        if recorded_requests is None:
                            print("Error: Re-injection failed. window.__recordedRequests is still None")
                        else:
                            print(f"Re-injection successful. Captured {len(recorded_requests)} requests")
                    elif len(recorded_requests) == 0:
                        print("Warning: No requests were captured")
                    else:
                        print(f"Successfully captured {len(recorded_requests)} requests")

                    # 将捕获的请求写入文件
                    with open("recorded_requests.json", "w", encoding='utf-8') as f:
                        json.dump(recorded_requests if recorded_requests else [], f, indent=2, ensure_ascii=False)

                    print(
                        f"Recorded {len(recorded_requests) if recorded_requests else 0} requests to recorded_requests.json")

                    return extracted_data
                else:
                    retry_count += 1
                    logging.warning("Max retries reached. No valid data found.")
                    continue

    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}")
    finally:
        if molmo:
            molmo.close()




def parse_points(description: str) -> List[Dict[str, any]]:
    """
    解析描述中的point和points标签，提取所有坐标对和其他信息。

    :param description: 包含point或points标签的描述字符串
    :return: 包含解析后信息的字典列表
    """
    xml_string = f"<root>{description}</root>"

    try:
        root = ET.fromstring(xml_string)
    except ET.ParseError:
        return []

    points_data = []

    for point in root.findall('.//point') + root.findall('.//points'):
        point_info = {
            'coordinates': [],
            'alt': point.get('alt', ''),
            'text': point.text.strip() if point.text else ''
        }

        attrs = point.attrib
        coord_pairs = []

        # 首先检查是否有 x 和 y 属性
        if 'x' in attrs and 'y' in attrs:
            coord_pairs.append((float(attrs['x']), float(attrs['y'])))

        # 然后检查是否有 x1, y1, x2, y2 等格式
        i = 1
        while f'x{i}' in attrs and f'y{i}' in attrs:
            coord_pairs.append((float(attrs[f'x{i}']), float(attrs[f'y{i}'])))
            i += 1

        # 如果仍然没有找到坐标，尝试解析属性值中的所有数字对
        if not coord_pairs:
            all_values = ' '.join(attrs.values())
            coord_pairs = [(float(x), float(y)) for x, y in re.findall(r'(\d+\.?\d*)\s+(\d+\.?\d*)', all_values)]

        point_info['coordinates'] = coord_pairs
        points_data.append(point_info)

    return points_data


from PIL import Image, ImageDraw, ImageFont
import random


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
                draw.ellipse([pixel_x - 12, pixel_y - 12, pixel_x + 12, pixel_y + 12], fill=color)

        # 绘制文本
        text = point.get('alt') or point.get('text', '')

        n_width, n_height = new_img.size
        new_img_draw = ImageDraw.Draw(new_img)
        new_img_draw.ellipse([((n_width - n_width + 55)-20) - 15, n_height-30 - 15, ((n_width - n_width + 55)-20) + 15, n_height-30 + 15], fill=color)
        new_img_draw.text(((n_width - n_width + 55), n_height-38), text, font=font, fill=color)
        new_img.paste(img, (0, 0))
        new_img.save("output.png", format="PNG")

# 使用函数


if __name__ == "__main__":
    start_time = time.time()
    question = "找到 手中的物品 并标记他们的位置"
    image = "test.jpeg"
    result = molmo_remote_process_image(question, image)
    end_time = time.time()
    generation_time = end_time - start_time
    logging.info("Result: %s", result)
    logging.info("parse_points: %s", parse_points(result['contents'][0]))
    draw_points_on_image(image, parse_points(result['contents'][0]))

    logging.info("Generation time: %s seconds", generation_time)
