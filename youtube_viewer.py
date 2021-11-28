import concurrent.futures.thread
import hashlib
import json
import logging
import os
import platform
import queue
import shutil
import sqlite3
import subprocess
import sys
import zipfile
import threading
import traceback
import requests
import selenium
import recordclass
import fake_headers
import itertools
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import closing
from datetime import datetime
from glob import glob
from random import choice, choices, randrange, shuffle, uniform, random, randint
from time import gmtime, sleep, strftime, time
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

import website
from config import create_config

log = logging.getLogger('werkzeug')
log.disabled = True

os.system("")

class styles:
  HEADER = '\033[95m'
  BOLD = '\033[1m'
  UNDERLINE = '\033[4m'

class colors:
  OKBLUE = ('\033[94m', "#3b8eea")
  OKCYAN = ('\033[96m', "#29b2d3")
  OKGREEN = ('\033[92m', "#23d18b")
  WARNING = ('\033[93m', "#ffff00")
  FAIL = ('\033[91m', "#f14c4c")
  NONE = ('', "#ffffff")
  ENDC = '\033[0m'

class AtomicCounter:
  def __init__(self, initial=0):
    self.value = initial
    self._lock = threading.Lock()

  def increment(self, num=1):
    with self._lock:
      self.value += num
      return self.value

ProxyInfo = recordclass.recordclass('ProxyInfo', 'type url')
BlacklistEntry = recordclass.recordclass('BlacklistEntry', 'weight time')

print(colors.OKGREEN[0] + """

Yb  dP  dP"Yb  88   88 888888 88   88 88""Yb 888888           
 YbdP  dP   Yb 88   88   88   88   88 88__dP 88__           
  8P   Yb   dP Y8   8P   88   Y8   8P 88""Yb 88""           
  dP    YbodP  `YbodP'   88   `YbodP' 88oodP 888888

            Yb  dP 88 88 8888 Yb    dP  88 88888 88""Yb 
             Yb  dP   88 88__  Yb  db  dP 88__   88__dP 
              YbdP    88 88""   YbdPYbdP  88""   88"Yb  
               YP     88 888888  YP  YP   888888 88  Yb 
""" + colors.ENDC)

print(colors.OKCYAN[0] + """
       [ GitHub : https://github.com/MShawon/YouTube-Viewer ]
""" + colors.ENDC)

SCRIPT_VERSION = '1.6.2'

proxy = None
status = None
server_running = False

urls = []
queries = []
hash_urls = None
hash_queries = None
start_time = None

driver_list = []
view = []
checked = {}
console = []
blacklist = {}
threads = 0
over_limit_sleep = 10
browser_count = AtomicCounter()
video_player_count = AtomicCounter()

terminated = False
log_reached_limit = False
log_proxy_events = 'console'
log_regular_events = 'console'
log_regular_errors = 'console'

BLACKLIST_DROP_PER_HOUR = 1.5
BLACKLIST_THRESHOLD = 1
MIN_BLACKLIST = 0.1
BAD_PROXY_WEIGHT = 1
SLOW_PROXY_WEIGHT = 0.5
OVER_LIMIT_SLEEP_UNIT = 4
VIEW_THREAD_RESERVE = 4

STAT_DATABASE = 'stats.db'
BLACKLIST_DATABASE = 'proxy_blacklist.db'

VIEWPORT = ['2560x1440', '1920x1080', '1440x900', '1536x864', '1366x768', '1280x1024', '1024x768']

SEARCH_ENGINES = ['https://search.yahoo.com/', 'https://duckduckgo.com/', 'https://www.google.com/',
      'https://www.bing.com/']
REFERERS = SEARCH_ENGINES + ['https://t.co/', '']

COMMANDS = [Keys.UP, Keys.DOWN, 'k', 'j', 'l', 't', 'c']

website.console = console
website.database = STAT_DATABASE

class PageLoadError(Exception):
  pass
class QueryError(Exception):
  pass

def check_update():
  api_url = 'https://api.github.com/repos/MShawon/YouTube-Viewer/releases/latest'
  response = requests.get(api_url, timeout=30)

  RELEASE_VERSION = response.json()['tag_name']

  if SCRIPT_VERSION != RELEASE_VERSION:
    print(styles.BOLD + 'Update Available!!! ' +
        f'YouTube Viewer version {SCRIPT_VERSION} needs to update to {RELEASE_VERSION} version.' + colors.ENDC)

def init_database():
  with closing(sqlite3.connect(STAT_DATABASE)) as connection:
    with closing(connection.cursor()) as cursor:
      cursor.execute("CREATE TABLE IF NOT EXISTS statistics (date TEXT, hours REAL)")
      connection.commit()
  with closing(sqlite3.connect(BLACKLIST_DATABASE)) as connection:
    with closing(connection.cursor()) as cursor:
      cursor.execute("CREATE TABLE IF NOT EXISTS blacklist (url TEXT PRIMARY KEY, weight REAL, time REAL)")
      cursor.execute("SELECT * FROM blacklist")
      now = time()
      while True:
        rows = cursor.fetchmany()
        if not rows: break
        for row in rows:
          blacklist[row[0]] = BlacklistEntry(row[1], row[2])
      connection.commit()

_stat_database_lock = threading.Lock()
def update_watch_time(amount):
  if amount <= 0:
    return
  today = str(datetime.today().date())
  with _stat_database_lock:
    with closing(sqlite3.connect(STAT_DATABASE, timeout=threads*10)) as connection:
      with closing(connection.cursor()) as cursor:
        try:
          cursor.execute("SELECT hours FROM statistics WHERE date = ?", (today,))
          previous = cursor.fetchone()[0]
          cursor.execute("UPDATE statistics SET hours = ? WHERE date = ?", (previous + amount, today))
        except Exception:
          cursor.execute("INSERT INTO statistics VALUES (?, ?)", (today, amount))
        connection.commit()

def add_blacklist(url, weight):
  if url in blacklist:
    entry = blacklist[url]
    update_blacklist(entry)
    entry.weight += weight
  else:
    blacklist[url] = BlacklistEntry(weight, time())

def ease_blacklist(multiplier=0.8):
  for entry in blacklist.values(): entry.weight *= multiplier

def update_blacklist(entry):
  now = time()
  entry.weight *= blacklist_drop_rate(now - entry.time)
  entry.time = now
  return entry.weight

def blacklisted(url, update=True):
  if url in blacklist:
    if update:
      return update_blacklist(blacklist[url]) >= BLACKLIST_THRESHOLD
    else:
      return blacklist[url].weight >= BLACKLIST_THRESHOLD

blacklist_drop_rate = lambda duration: (1/BLACKLIST_DROP_PER_HOUR)**(duration/3600)

def combined_log(level, *text_tups):
  if level and not terminated:
    timestamp = datetime.now().strftime("[%d-%b-%Y %H:%M:%S] ")
    text_tups = [(colors.NONE, timestamp), *text_tups]
    print(''.join([color[0] + msg for color, msg in text_tups]) + colors.ENDC)
    if api and level == 'html':
      if len(console) > 50:
        console.pop(0)
      html = ''.join([f'<span style="color:{key[1]}"> {value} </span>' for key, value in text_tups])
      console.append(html)

def get_traceback(limit=None):
  return traceback.format_exc(limit=1 if terminated else limit)

def wait_for_video(driver):
  try:
    WebDriverWait(driver, 30).until(EC.visibility_of_element_located(
      (By.XPATH, '//ytd-player[@id="ytd-player"]')))
  except selenium.common.exceptions.TimeoutException:
    raise PageLoadError()

def spoof_referer(driver, referer, url):
  try:
    if referer:
      driver.get(referer)
      driver.execute_script(
        "window.location.href = '{}';".format(url))
    else:
      driver.get(url)
  except (selenium.common.exceptions.TimeoutException, selenium.common.exceptions.WebDriverException):
    raise PageLoadError()

class Video:
  def __init__(self, id, info, fake_watch):
    self.id = id
    self.title = info['title']
    self.fake_watch = fake_watch
    self.routes = [('url', url) for url in info['urls']] + [('search', kw) for kw in info['searches']]
  def open(self, identifier, driver):
    route = choice(self.routes)
    if route[0] == 'search':
      spoof_referer(driver, choice(SEARCH_ENGINES), "https://www.youtube.com/")
      try:
        WebDriverWait(driver, 30).until(EC.visibility_of_element_located(
          (By.CSS_SELECTOR, 'input#search')))
      except selenium.common.exceptions.TimeoutException:
        raise PageLoadError()
      bypass_consent(identifier, driver)
      if not search_video(driver, route[1], [self]):
        combined_log(log_regular_errors, (colors.FAIL, identifier + f"Search not found: {route[1]} :::: {self.title}. Fallback to url"))
        route = self.routes[0]
        if route[0] != 'url':
          raise Exception("Can't find a url for video")
      else:
        wait_for_video(driver)
        return
    if route[0] == 'url':
      spoof_referer(driver, choice(REFERERS), route[1])
      wait_for_video(driver)
      bypass_consent(identifier, driver)
    else:
      raise Exception("Invalid route type: " + route[0])

class Videos:
  def __init__(self):
    self.load()
    self.hash = self.get_hash()
  def load(self):
    with open('videos.json', 'r', encoding='utf-8') as fp:
      video_dict = json.load(fp)
    with open('fake_watch_videos.json', 'r', encoding='utf-8') as fp:
      fake_watch_dict = json.load(fp)
    if not video_dict:
      combined_log("html", (colors.FAIL, f"Your videos.json is empty!"))
      sys.exit()
    self.targeted_videos = [Video(id, info, False) for id, info in video_dict.items()]
    print(colors.OKGREEN[0] + f'{len(self.targeted_videos)} videos loaded' + colors.ENDC)
    self.all_videos = self.targeted_videos + [Video(id, info, True) for id, info in fake_watch_dict.items()]*3
  def get_hash(self):
    hash = hashlib.md5()
    with open("videos.json", "rb") as f:
      hash.update(f.read())
    with open("fake_watch_videos.json", "rb") as f:
      hash.update(f.read())
    return hash.hexdigest()
  def detect_changes(self):
    new_hash = self.get_hash()
    if new_hash != self.hash:
      print("Reloading videos...")
      self.load()
      self.hash = new_hash

def gather_proxy():
  proxies = []
  print(colors.OKGREEN[0] + 'Scraping proxies ...' + colors.ENDC)

  link_list = ['https://raw.githubusercontent.com/clarketm/proxy-list/master/proxy-list-raw.txt',
         'https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt',
         'https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/socks4.txt',
         'https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/socks5.txt',
         'https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/proxy.txt',
         'https://raw.githubusercontent.com/sunny9577/proxy-scraper/master/proxies.txt']

  for link in link_list:
    response = requests.get(link)
    output = response.content.decode()
    proxy = output.split('\n')
    proxies += proxy
    print(colors.OKGREEN[0] +
        f'{len(proxy)} proxies gathered from {link}' + colors.ENDC)
  return [ProxyInfo(proxy_type, url) for url in proxies]

def needed_browsers():
  return max(0, browser_ratio * (max_video_players - video_player_count.value) + video_player_count.value)

def load_proxy(source, proxy_type):
  proxies = []
  def add_line(line):
    if line:
      if line.count(':') == 3:
        split = line.split(':')
        line = f'{split[2]}:{split[-1]}@{split[0]}:{split[1]}'
      proxies.append(line)
  if 'http://' in source or 'https://' in source:
    output = requests.get(source).content.decode()
    for line in output.split('\r\n' if '\r\n' in output else '\n'):
      add_line(line)
  else:
    with open(source, encoding="utf-8") as fh:
      for line in fh:
        add_line(line.strip())
  return [ProxyInfo(proxy_type, url) for url in proxies]

def check_proxy(headers, proxy):
  try:
    if category == 'free':
      proxy_dict = {
        "http": f"{proxy.type}://{proxy.url}",
        "https": f"{proxy.type}://{proxy.url}",
      }
      response = requests.get(
        'https://www.youtube.com/', headers=headers, proxies=proxy_dict, timeout=30)
      return response.status_code != 200
  except Exception:
    return True

def get_driver(agent, proxy):
  ostype = platform.system()
  if ostype == 'Windows':
    null_path = 'nul'
  elif ostype == 'Linux':
    null_path = '/dev/null'
  elif ostype == 'Darwin':
    null_path = '/dev/null'
  else:
    raise Exception("Operating systemc not supported")
  options = selenium.webdriver.FirefoxOptions()
  options.headless = True

  proxy_split = proxy.url.split(':')
  options.set_preference("network.proxy.type", 1)
  if 'socks' in proxy.type:
    options.set_preference("network.proxy.socks", proxy_split[0])
    options.set_preference("network.proxy.socks_port", int(proxy_split[1]))
    if proxy.type == 'socks4':
      options.set_preference("network.proxy.socks_version", 4)
    elif proxy.type == 'socks5':
      options.set_preference("network.proxy.socks_version", 5)
  elif 'http' in proxy.type:
    options.set_preference("network.proxy.http", proxy_split[0])
    options.set_preference("network.proxy.http_port", int(proxy_split[1]))
    options.set_preference("network.proxy.ssl", proxy_split[0])
    options.set_preference("network.proxy.ssl_port", int(proxy_split[1]))

  sizes = choice(VIEWPORT).split('x')
  options.set_preference("media.volume_scale", "0.01")
  options.set_preference("general.useragent.override", agent)
  options.set_preference("media.default_volume", "0.01")
  options.set_preference("media.autoplay.default", 0)
  options.set_preference("browser.cache.disk.enable", "false")
  options.set_preference("browser.cache.disk_cache_ssl", "false")
  options.set_preference("browser.cache.memory.enable", "false")
  options.set_preference("browser.cache.offline.enable", "false")
  options.set_preference("browser.cache.insecure.enable", "false")
  options.set_preference("media.block-autoplay-until-in-foreground", "false")
  options.set_preference("media.peerconnection.enabled", "false")
  options.set_preference("privacy.resistfingerprinting", "true")
  #options.set_preference("security.ssl3.rsa_des_ede3_sha", "false")
  #options.set_preference("security.ssl.requrie_safe_negotiation", "true")
  #options.set_preference("security.tls.version.min", "3")
  #options.set_preference("security.tls.enable_0rtt_data", "false")
  options.set_preference("geo.enabled", "false")
  options.set_preference("plugin.scan.plid.all", "false")
  options.set_preference("browser.newtabpage.activity-stream.feeds.telemetry browser.newtabpage.activity-stream.telemetry", "false")
  options.set_preference("browser.pingcentre.telemetry", "false")
  options.set_preference("devtools.onboarding.telemetry-logged", "false")
  options.set_preference("media.wmf.deblacklisting-for-telemetry-in-gpu-process", "false")
  options.set_preference("toolkit.telemetry.archive.enabled", "false")
  options.set_preference("toolkit.telemetry.bhrping.enabled", "false")
  options.set_preference("toolkit.telemetry.firstshutdownping.enabled", "false")
  options.set_preference("toolkit.telemetry.hybridcontent.enabled", "false")
  options.set_preference("toolkit.telemetry.newprofileping.enabled", "false")
  options.set_preference("toolkit.telemetry.unified", "false")
  options.set_preference("toolkit.telemetry.updateping.enabled", "false")
  options.set_preference("toolkit.telemetry.shutdownpingsender.enabled", "false")
  #options.set_preference("webgl.disabled", "true")
  options.set_preference("privacy.firstparty.isolate", "true")
  options.set_preference("security.ssl.enable_false_start", "false")
  caps = selenium.webdriver.DesiredCapabilities().FIREFOX
  caps["pageLoadStrategy"] = "eager"
  driver = selenium.webdriver.Firefox(firefox_binary=firefox_path, options=options, service_log_path=null_path)
  driver.set_window_size(sizes[0], sizes[1])
  return driver

def personalization(driver):
  search = driver.find_element_by_xpath(
    f'//button[@aria-label="Turn {choice(["on","off"])} Search customization"]')
  driver.execute_script("arguments[0].scrollIntoView();", search)
  search.click()

  history = driver.find_element_by_xpath(
    f'//button[@aria-label="Turn {choice(["on","off"])} YouTube History"]')
  driver.execute_script("arguments[0].scrollIntoView();", history)
  history.click()

  ad = driver.find_element_by_xpath(
    f'//button[@aria-label="Turn {choice(["on","off"])} Ad personalization"]')
  driver.execute_script("arguments[0].scrollIntoView();", ad)
  ad.click()

  confirm = driver.find_element_by_xpath('//button[@jsname="j6LnYe"]')
  driver.execute_script("arguments[0].scrollIntoView();", confirm)
  confirm.click()


def bypass_consent(identifier, driver):
  try:
    consent = driver.find_element_by_xpath("//button[@jsname='higCR']")
  except NoSuchElementException:
    try:
      consent = driver.find_element_by_xpath("//input[@type='submit' and @value='I agree']")
    except NoSuchElementException:
      return
  combined_log(log_regular_events, (colors.OKBLUE, identifier + f"Bypassing consent..."))
  driver.execute_script("arguments[0].scrollIntoView();", consent)
  consent.click()
  if 'consent' in driver.current_url:
    personalization(driver)

def bypass_signin(driver):
  for _ in range(10):
    sleep(2)
    try:
      nothanks = driver.find_element_by_class_name(
        "style-scope.yt-button-renderer.style-text.size-small")
      nothanks.click()
      sleep(1)
      driver.switch_to.frame(driver.find_element_by_id("iframe"))
      iagree = driver.find_element_by_id('introAgreeButton')
      iagree.click()
      driver.switch_to.default_content()
    except Exception:
      try:
        driver.switch_to.frame(driver.find_element_by_id("iframe"))
        iagree = driver.find_element_by_id('introAgreeButton')
        iagree.click()
        driver.switch_to.default_content()
      except Exception:
        pass


def bypass_popup(driver):
  try:
    agree = WebDriverWait(driver, 5).until(EC.visibility_of_element_located(
      (By.XPATH, '//*[@aria-label="Agree to the use of cookies and other data for the purposes described"]')))
    driver.execute_script(
      "arguments[0].scrollIntoView();", agree)
    sleep(1)
    agree.click()
  except Exception:
    pass


def bypass_other_popups(driver):
  labels = ['Got it', 'Skip trial', 'No thanks', 'Dismiss', 'Not now']
  shuffle(labels)

  for label in labels:
    try:
      driver.find_element_by_xpath(f"//*[@id='button' and @aria-label='{label}']").click()
    except Exception:
      pass


def skip_stuff(identifier, driver):
  bypass_popup(driver)
  try:
    WebDriverWait(driver, 15).until(EC.element_to_be_clickable(
      (By.CLASS_NAME, "ytp-ad-preview-container")))
  except Exception:
    combined_log(log_regular_events, (colors.OKBLUE, identifier + f"No ads found"))
  else:
    try:
      combined_log(log_regular_events, (colors.OKBLUE, identifier + "Skipping Ads..."))
      skip_button = WebDriverWait(driver, 20).until(EC.element_to_be_clickable(
          (By.CLASS_NAME, "ytp-ad-skip-button")))
      sleep(uniform(0.1, 5))
      skip_button.click()
    except Exception as e:
      combined_log(log_regular_errors, (colors.OKBLUE, identifier + f"Ad skipping exception: {repr(e)}"))
  bypass_other_popups(driver)

def type_keyword(driver, keyword, retry=False):
  input_keyword = driver.find_element_by_css_selector('input#search')

  if retry:
    for _ in range(10):
      try:
        input_keyword.click()
        break
      except Exception:
        sleep(5)
        pass

  input_keyword.clear()
  for letter in keyword:
    input_keyword.send_keys(letter)
    sleep(uniform(.1, .4))

  if randrange(2):
    input_keyword.send_keys(Keys.ENTER)
  else:
    try:
      driver.find_element_by_xpath(
        '//*[@id="search-icon-legacy"]').click()
    except Exception:
      driver.execute_script(
        'document.querySelector("#search-icon-legacy").click()')

def find_video(driver, videos):
  for i in range(10):
    try:
      container = WebDriverWait(driver, 3).until(EC.visibility_of_element_located(
        (By.XPATH, f'//ytd-item-section-renderer[{i}]')))
    except selenium.common.exceptions.TimeoutException:
      container = driver
    for video in videos:
      try:
        video_element = container.find_element_by_xpath(f'//*[@title="{video.title}"]')
      except NoSuchElementException:
        continue
      driver.execute_script("arguments[0].scrollIntoView();", video_element)
      sleep(1)
      bypass_popup(driver)
      try:
        video_element.click()
      except Exception:
        driver.execute_script("arguments[0].click();", video_element)
      return video
    sleep(2)
    WebDriverWait(driver, 30).until(EC.visibility_of_element_located(
      (By.TAG_NAME, 'body'))).send_keys(Keys.CONTROL, Keys.END)

def search_video(driver, keyword, videos):
  try:
    type_keyword(driver, keyword)
  except Exception:
    try:
      bypass_popup(driver)
      type_keyword(driver, keyword, retry=True)
    except selenium.common.exceptions.TimeoutException:
      raise PageLoadError()
  return find_video(driver, videos)

def play_video(driver):
  try:
    driver.find_element_by_css_selector('[title^="Pause (k)"]')
  except Exception:
    try:
      driver.find_element_by_css_selector(
        'button.ytp-large-play-button.ytp-button').send_keys(Keys.ENTER)
    except Exception:
      try:
        driver.find_element_by_css_selector(
          '[title^="Play (k)"]').click()
      except Exception:
        try:
          driver.execute_script(
            "document.querySelector('button.ytp-play-button.ytp-button').click()")
        except Exception:
          pass

def play_music(driver):
  try:
    driver.find_element_by_xpath(
      '//*[@id="play-pause-button" and @title="Pause"]')
  except Exception:
    try:
      driver.find_element_by_xpath(
        '//*[@id="play-pause-button" and @title="Play"]').click()
    except Exception:
      driver.execute_script(
        'document.querySelector("#play-pause-button").click()')

def play(identifier, driver, fake_watch = False):
  if "music.youtube.com" in driver.current_url:
    content_type = 'Music'
    play_music(driver)
    view_stat = 'Music'
  else:
    content_type = 'Video'
    play_video(driver)
    if bandwidth:
      save_bandwidth(driver)
    change_playback_speed(driver)
    view_stat = WebDriverWait(driver, 30).until(EC.visibility_of_element_located(
      (By.XPATH, '//span[@class="view-count style-scope ytd-video-view-count-renderer"]'))).text

  if fake_watch:
    sleep(uniform(5, 10))
  elif 'watching' in view_stat:
    error = 0
    while True:
      view_stat = driver.find_element_by_xpath(
        '//span[@class="view-count style-scope ytd-video-view-count-renderer"]').text
      if 'watching' in view_stat:
        combined_log(log_regular_events, (colors.OKGREEN, identifier + "Stream found, "), (colors.OKCYAN, f"{view_stat} "))
      else:
        error += 1
      play_video(driver)
      random_command(driver)
      if error == 5:
        break
      sleep(60)
      update_watch_time(60/3600)
    return
  else:
    try:
      current_url = driver.current_url
      video_len = 0
      while video_len == 0:
        video_len = driver.execute_script(
          "return document.getElementById('movie_player').getDuration()")
      video_len = video_len*uniform(minimum, maximum)

      duration = strftime("%Hh:%Mm:%Ss", gmtime(video_len))
      combined_log(log_regular_events, (colors.OKGREEN, identifier + f"{content_type} found, Watch Duration : {duration} "))
    except Exception:
      combined_log('html', (colors.FAIL, identifier + "Suppressed exception before playing: {get_traceback()}"))

    update_interval = 5
    update_counter = 1
    prev_time = 0
    for _ in range(round(video_len/2)):
      sleep(uniform(0.1, 10))
      current_time = driver.execute_script(
        "return document.getElementById('movie_player').getCurrentTime()")
      if update_counter % update_interval:
        update_counter += 1
      elif database:
        update_watch_time((current_time - prev_time)/3600)
        prev_time = current_time
      if content_type == 'Video':
        play_video(driver)
        random_command(driver)
      elif content_type == 'Music':
        play_music(driver)
      if current_time > video_len or driver.current_url != current_url:
        break
  if randrange(2):
    driver.find_element_by_id('movie_player').send_keys('k')

def save_bandwidth(driver):
  try:
    driver.find_element_by_css_selector(
      "button.ytp-button.ytp-settings-button").click()
    driver.find_element_by_xpath(
      "//div[contains(text(),'Quality')]").click()

    random_quality = choice(['144p', '240p', '360p'])
    quality = WebDriverWait(driver, 10).until(EC.element_to_be_clickable(
      (By.XPATH, f"//span[contains(string(),'{random_quality}')]")))
    driver.execute_script(
      "arguments[0].scrollIntoView();", quality)
    quality.click()

  except Exception:
    try:
      driver.find_element_by_xpath(
        '//*[@id="container"]/h1/yt-formatted-string').click()
    except Exception:
      pass


def change_playback_speed(driver):
  if playback_speed == 2:
    driver.find_element_by_id('movie_player').send_keys('<'*randrange(3) + 1)
  elif playback_speed == 3:
    driver.find_element_by_id('movie_player').send_keys('>'*randrange(3) + 1)


def random_command(driver):
  bypass_other_popups(driver)
  option = choices([1, 2], cum_weights=(0.7, 1.00), k=1)[0]
  if option == 2:
    command = choice(COMMANDS)
    if command in ['m', 't', 'c']:
      driver.find_element_by_id('movie_player').send_keys(command)
    elif command == 'k':
      if randrange(2):
        driver.find_element_by_id('movie_player').send_keys(command)
      driver.execute_script(
        f'document.querySelector("#comments"){choices(["scrollIntoView", "scrollIntoView"])}();')
      sleep(uniform(4, 10))
      driver.execute_script(
        'document.querySelector("#movie_player").scrollIntoView();')
    else:
      driver.find_element_by_id('movie_player').send_keys(command*(randrange(5)+1))

def quit_driver(driver):
  driver_list.remove(driver)
  driver.quit()

def view_thread(identifier, proxy, videos):
  try:
    videos.detect_changes()
    headers = fake_headers.Headers(headers=True).generate()
    if browser_count.value < needed_browsers() and video_player_count.value < max_video_players:
      if check_proxy(headers, proxy):
        add_blacklist(proxy.url, BAD_PROXY_WEIGHT)
        combined_log(log_proxy_events, (colors.FAIL, identifier + f"{proxy.type} --> Bad proxy"))
        return True
    else:
      combined_log(log_reached_limit, (colors.OKBLUE, identifier + f"Reached browser count limit"))
      sleep(over_limit_sleep)
      return

    if browser_count.value < needed_browsers() and not terminated:
      combined_log(log_proxy_events, (colors.OKGREEN, identifier + f"{proxy.type} --> Good Proxy, Opening a new driver"))
      driver = get_driver(headers['User-Agent'], proxy)
      driver_list.append(driver)
      try:
        browser_count.increment()
        sleep(2)
        for _ in range(4):
          current = choice(videos.all_videos)
          current.open(identifier, driver)
          if video_player_count.value < max_video_players:
            try:
              video_player_count.increment()
              skip_stuff(identifier, driver)
              play(identifier, driver, current.fake_watch)
              for idx in range(randint(3, 5)):
                next = find_video(driver, videos.targeted_videos)
                if not next:
                  combined_log('html', (colors.FAIL, identifier + f"Can't find a recommended video from {current.title}, opening a new one"))
                  current = choice(videos.targeted_videos)
                  current.open(identifier, driver)
                else:
                  combined_log(log_regular_events, (colors.OKBLUE, identifier + f"Jumped '{current.title}' --> '{next.title}'"))
                  current = next
                skip_stuff(identifier, driver)
                play(identifier, driver, current.fake_watch)
            finally:
              video_player_count.increment(-1)
          else:
            break
        else:
          combined_log(log_reached_limit, (colors.OKBLUE, identifier + f"Reached video player limit"))
          sleep(over_limit_sleep)
          return
        combined_log(log_regular_events, (colors.OKBLUE, identifier + "Closing video player"))
      except PageLoadError:
        add_blacklist(proxy.url, SLOW_PROXY_WEIGHT)
        combined_log(log_regular_errors, (colors.FAIL, identifier + f"Can't load YouTube! Slow internet speed or Stuck at recaptcha"))
        return True
      except selenium.common.exceptions.WebDriverException:
        add_blacklist(proxy.url, SLOW_PROXY_WEIGHT)
        combined_log(log_regular_errors, (colors.FAIL, identifier + f"WebDriverException: {get_traceback(2)}"))
        return True
      except Exception:
        combined_log(log_regular_errors, (colors.FAIL, identifier + f"Watch loop exception : {get_traceback()}"))
      finally:
        quit_driver(driver)
        browser_count.increment(-1)
  except Exception:
    combined_log(log_regular_errors, (colors.FAIL, identifier + f"Main viewer : {get_traceback()}"))
  finally:
    if not terminated:
      spawn_view_thread()

def exception_wrapper(msg, func, *args):
  try:
    func(*args)
  except Exception:
    combined_log('html', (colors.FAIL, f"{msg}: {get_traceback()}"))

def start_server():
  global server_running
  if api and not server_running:
    server_running = True
    website.start_server(host=host, port=port)

def check_monitored_files():
  while not terminated:
    sleep(FILE_CHECK_PERIOD)

def clean_exit(executor):
  try:
    with closing(sqlite3.connect(BLACKLIST_DATABASE, timeout=threads*10)) as connection:
      with closing(connection.cursor()) as cursor:
        for url, entry in blacklist.items():
          if entry.weight >= MIN_BLACKLIST:
            cursor.execute("""INSERT INTO blacklist(url, weight, time) VALUES (?1, ?2, ?3)
                ON CONFLICT(url) DO UPDATE SET weight = ?2, time = ?3""", (url, *entry))
          else:
            cursor.execute("DELETE FROM blacklist WHERE url=?", (url,))
        connection.commit()
    global terminated
    terminated = True
    executor.shutdown(wait=True)
    for driver in driver_list:
      driver.quit()
    if server_future:
      print('Trying to stop the server')
      server_future = None
      server_future.cancel()
  except:
    traceback.print_exc()
  
def process_cmd(cmd):
  cmd = cmd.lower()
  global max_video_players
  if cmd in ['status', 's']:
    print(rf"""Browser count: {browser_count.value}
Video player count: {video_player_count.value}/{max_video_players}""")
  elif cmd[1:] in ['player', 'players', 'p']:
    if cmd[0] == '+':
      max_video_players += 1
    elif cmd[0] == '-':
      max_video_players -= 1
    elif cmd[0] == '0':
      max_video_players = 0
    elif cmd[0] != '?':
      print("Invalid operator: {cmd[0]}")
    print(f"Max video players: {max_video_players}")
  elif cmd:
    print(f"Invalid command: {cmd}")

def periodic_update():
  global proxy_list
  proxy_list = refresh_proxies()
  while True:
    good_count = sum((1 for proxy in proxy_list if not blacklisted(proxy.url, False)))
    if good_count >= VIEW_THREAD_RESERVE * proxy_thread_count:
      break
    ease_blacklist()
  print(colors.OKCYAN[0] + f'Good proxies : {good_count}' + colors.ENDC)
  shuffle(videos.targeted_videos)
  shuffle(videos.all_videos)

def main():
  global start_time
  global proxy_list
  global threads
  global futures
  global server_future
  global spawn_view_thread

  start_time = time()
  extra_threads = 2 if api else 1

  with ThreadPoolExecutor(max_workers=proxy_thread_count + extra_threads) as executor:
    try:
      def add_thread(msg, func, *args):
        return executor.submit(exception_wrapper, msg, func, *args)
      if api:
        server_future = add_thread("Web server error", start_server)
      spawn_lock = threading.Lock()
      current_proxy_idx = 0
      def spawn_view_thread():
        nonlocal current_proxy_idx
        try:
          while True:
            with spawn_lock:
              if not current_proxy_idx:
                periodic_update()
              idx = current_proxy_idx
              current_proxy_idx = (current_proxy_idx + 1) % len(proxy_list)
            proxy = proxy_list[idx]
            if proxy.type:
              if not blacklisted(proxy.url):
                identifier = f"Num {idx}".rjust(8) + f" | {proxy.url.center(21)} | "
                add_thread("Video viewer error", view_thread, identifier, proxy, videos)
                return
            else:
              combined_log('html', (colors.FAIL, "Proxy type not found"))
        except Exception:
          traceback.print_exc()
      for _ in range(VIEW_THREAD_RESERVE * proxy_thread_count):
        spawn_view_thread()
      while True:
        try:
          process_cmd(input())
        except KeyboardInterrupt:
          try:
            global terminated
            terminated = True
            print("INTERRUPT")
            clean_exit(executor)
            executor._threads.clear()
            concurrent.futures.thread._threads_queues.clear()
          finally:
            sys.exit()
        except Exception:
          combined_log('html', (colors.FAIL, f"CLI error: {get_traceback()}"))
    except Exception:
      traceback.print_exc()

def refresh_proxies():
  proxy_conf = config["proxy"]
  if category == 'gather':
    proxy_list = gather_proxy()
  else:
    proxy_list = []
    if "http_source" in proxy_conf:
      proxy_list += load_proxy(proxy_conf["http_source"], 'http')
    if "socks4_source" in proxy_conf:
      proxy_list += load_proxy(proxy_conf["socks4_source"], 'socks4')
    if "socks5_source" in proxy_conf:
      proxy_list += load_proxy(proxy_conf["socks5_source"], 'socks5')
  shuffle(proxy_list)
  print(colors.OKCYAN[0] + f'Total proxies : {len(proxy_list)}' + colors.ENDC)
  return proxy_list


if __name__ == '__main__':
  check_update()
  init_database()
  videos = Videos()

  if os.path.isfile('config.json'):
    with open('config.json', 'r') as openfile:
      config = json.load(openfile)
  else:
    create_config()

  with open('config.json', 'r') as openfile:
    config = json.load(openfile)

  global max_browsers
  api = config["http_api"]["enabled"]
  host = config["http_api"]["host"]
  port = config["http_api"]["port"]
  database = config["database"]
  firefox_path = config["firefox_path"]
  minimum = config["minimum_percent"] / 100
  maximum = config["maximum_percent"] / 100
  category = config["proxy"]["category"]
  proxy_type = config["proxy"]["proxy_type"]
  auth_required = config["proxy"]["authentication"]
  background = config["background"]
  bandwidth = config["bandwidth"]
  playback_speed = config["playback_speed"]
  proxy_thread_count = config["proxy_thread_count"]
  browser_ratio = config["browser_per_video_player"]
  max_video_players = config["video_player_count"]
  over_limit_sleep = proxy_thread_count*OVER_LIMIT_SLEEP_UNIT

  if auth_required and background:
    print(colors.FAIL[0] +
        "Premium proxy needs extension to work. Chrome doesn't support extension in Headless mode." + colors.ENDC)
    input(colors.WARNING[0] +
        f"Either use proxy without username & password or disable headless mode " + colors.ENDC)
    sys.exit()
  while len(view) < views:
    try:
      main()
    except KeyboardInterrupt:
      sys.exit()
