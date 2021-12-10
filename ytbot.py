import hashlib
from pathlib import Path
import json
import os
import re
import sqlite3
import subprocess
import sys
import threading
import traceback
import requests
import selenium
import fake_useragent
import concurrent.futures
import time
import random
import datetime
import base64
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

import website
import proxy_scraper
import proxy_checker

detailed_proxy_errors = True
log_reached_limit = False
log_proxy_events = 'temp'
log_regular_events = 'temp'
log_regular_errors = 'temp'

OVER_LIMIT_SLEEP_UNIT = 4

STAT_DATABASE = 'stats.db'
COOLDOWN_DATABASE = 'proxy_cooldowns.db'

VIEWPORT = ['2560x1440', '1920x1080', '1920x1080', '1440x900', '1536x864', '1366x768', '1280x1024']
SEARCH_ENGINES = ['https://search.yahoo.com/', 'https://duckduckgo.com/', 'https://www.google.com/', 'https://www.bing.com/', '', '']
REFERERS = SEARCH_ENGINES + ['https://t.co/']
GOOGLE_LINK_TEMPLATE = "https://www.google.com/url?sa=t&rct=j&q=&esrc=s&source=video&cd=&url={url}"
YOUTUBE_LINK_TEMPLATE = "https://www.youtube.com/watch?v={id}"
YOUTU_BE_LINK_TEMPLATE = "https://youtu.be/{id}"

os.system("")
website.database = STAT_DATABASE
start_time = time.time()

################ UTILS ################

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
  ENDC = '\033[0m'
  NONE = (ENDC, "#ffffff")

class AtomicCounter:
  def __init__(self, initial=0):
    self.value = initial
    self._lock = threading.Lock()
  def increment(self, num=1):
    with self._lock:
      self.value += num
      return self.value

uniform_sleep = lambda min, max: time.sleep(random.uniform(min, max))
list_wrap = lambda item: item if isinstance(item, list) else [item]
today = lambda: str(datetime.datetime.today().date())

def get_null_path():
  if os.name == 'nt':
    return 'nul'
  elif os.name == 'posix':
    return '/dev/null'
  else:
    raise Exception("Operating system not supported: " + os.name)

def take_screenshot(driver):
  if not terminated:
    Path("screenshots").mkdir(parents=True, exist_ok=True)
    path = datetime.datetime.now().strftime("screenshots/%d-%b-%Y %H-%M-%S.png")
    driver.get_screenshot_as_file(path)

class LoadingError(Exception): pass
class FirstActionError(LoadingError): pass
class FirstPageError(FirstActionError): pass
class TerminatedError(Exception): pass

def first_page_wrap(driver, url):
  try:
    driver.get(url)
  except (selenium.common.exceptions.TimeoutException, selenium.common.exceptions.WebDriverException):
    try:
      driver.get(url)
    except (selenium.common.exceptions.TimeoutException, selenium.common.exceptions.WebDriverException):
      raise FirstPageError()

def first_action_wrap(driver, condition):
  try:
    return WebDriverWait(driver, 20).until(condition)
    driver.get(url)
  except (selenium.common.exceptions.TimeoutException):
    raise FirstActionError()

def combined_log(level, *text_tups):
  if level and not terminated:
    timestamp = datetime.datetime.now().strftime("[%d-%b-%Y %H:%M:%S] ")
    text_tups = [timestamp, *text_tups]
    text_tups = [(colors.NONE, tup) if isinstance(tup, str) else tup for tup in text_tups]
    print(''.join([color[0] + msg for color, msg in text_tups]) + colors.ENDC)
    if web_interface and level == 'persist':
      if log_file:
        log_file.write(''.join([msg for _, msg in text_tups]) + '\n')
      if len(website.console) > 50:
        website.console.pop(0)
      html = ''.join([f'<span style="color:{key[1]}"> {value} </span>' for key, value in text_tups])
      website.console.append(html)

def error_log(level, text):
  combined_log(level, (colors.FAIL, text))

def wait_for_video(driver):
  try:
    WebDriverWait(driver, 100).until(EC.visibility_of_element_located(
      (By.XPATH, '//ytd-player[@id="ytd-player"]')))
  except selenium.common.exceptions.TimeoutException:
    raise LoadingError("Youtube video player failed to load")

def spoof_referer(driver, referer, url):
  if referer:
    first_page_wrap(driver, referer)
    driver.execute_script(
      "window.location.href = '{}';".format(url))
  else:
    first_page_wrap(driver, url)

def get_fallback_links(video_id):
  return [ YOUTU_BE_LINK_TEMPLATE.format(id=video_id), YOUTUBE_LINK_TEMPLATE.format(id=video_id) ]

################ DATABASE ################

def init_database():
  global watch_time
  global og_watch_time
  global views
  global og_views
  cursor = stats_db.cursor()
  cursor.execute("CREATE TABLE IF NOT EXISTS statistics (date TEXT, hours REAL, views INTEGER)")
  try:
    cursor.execute("SELECT hours, views FROM statistics WHERE date = ?", (today(),))
    watch_time = AtomicCounter(cursor.fetchone()[0])
    views = AtomicCounter(cursor.fetchone()[1])
  except Exception:
    cursor.execute("INSERT INTO statistics VALUES (?, ?, ?)", (today(), 0, 0))
    watch_time = AtomicCounter(0)
    views = AtomicCounter(0)
  og_watch_time = watch_time.value
  og_views = views.value
  stats_db.commit()

def update_database():
  global stats_db, cooldowns
  stats_db = sqlite3.connect(STAT_DATABASE)
  cooldowns = Cooldowns()
  try:
    init_database()
    while True:
      time.sleep(15)
      try:
        stats_db.execute("UPDATE statistics SET hours = ? WHERE date = ?", (watch_time.value, today()))
        stats_db.commit()
        cooldowns.commit()
        videos.detect_changes()
      except Exception:
        error_log('persist', f"Database update error: {traceback.format_exc()}")
      if terminated:
        break
  finally:
    stats_db.close()
    cooldowns.db.close()

################ COOLDOWNS ################

COOLDOWN_PER_HOUR = 1
COOLDOWN_THRESHOLD = 2
MIN_COOLDOWN = 0.1
BAD_PROXY_COOLDOWN = 2
SLOW_PROXY_COOLDOWN = 1
BAD_ANON_COOLDOWN = 48
WATCH_COOLDOWN = 12

class CooldownEntry:
  def __init__(self, weight, time):
    self.weight = weight
    self.time = time
class Cooldowns:
  def __init__(self):
    self.db = sqlite3.connect(COOLDOWN_DATABASE)
    self.entries = {}
    self._lock = threading.Lock()
    cursor = self.db.cursor()
    cursor.execute("""CREATE TABLE IF NOT EXISTS cooldowns
        (url TEXT PRIMARY KEY, weight REAL, time REAL)""")
    self.db.commit()
    cursor.execute("SELECT * FROM cooldowns")
    now = time.time()
    while True:
      rows = cursor.fetchmany()
      if not rows: break
      for row in rows:
        self.entries[row[0]] = CooldownEntry(row[1], row[2])
  def add(self, url, weight):
    if url in self.entries:
      entry = self.entries[url]
      self.update(entry)
      entry.weight += weight
      self.entries[url] = entry
    else:
      with self._lock:
        self.entries[url] = CooldownEntry(weight, time.time())
  def update(self, entry):
    now = time.time()
    entry.weight -= COOLDOWN_PER_HOUR*(now - entry.time)/3600
    entry.time = now
    return entry.weight
  def blocks(self, url, update=True):
    if url in self.entries:
      if update:
        return self.update(self.entries[url]) >= COOLDOWN_THRESHOLD
      else:
        return self.entries[url].weight >= COOLDOWN_THRESHOLD
  def commit(self):
    cursor = self.db.cursor()
    with self._lock:
      for url, entry in self.entries.items():
        if entry.weight >= MIN_COOLDOWN:
          cursor.execute("""INSERT INTO cooldowns(url, weight, time) VALUES (?1, ?2, ?3)
              ON CONFLICT(url) DO UPDATE SET weight = ?2, time = ?3""",
              (url, entry.weight, entry.time))
        else:
          cursor.execute("DELETE FROM cooldowns WHERE url=?", (url,))
    self.db.commit()

################ PROXIES ################

PROXY_RESERVE = 4
PROXY_CHECK_ORDER = {
  None: ['http', 'socks4', 'socks5'],
  'http': ['http', 'socks4', 'socks5'],
  'socks4': ['socks4', 'socks5', 'http'],
  'socks5': ['socks5', 'socks4', 'http'],
}
class ProxyInfo:
  def __init__(self, type, url):
    self.type = type
    self.url = url
class Proxies:
  def __init__(self):
    self._current_idx = 0
    self._idx_lock = threading.Lock()
    self.checker = proxy_checker.Checker()
    self.hash = None

  def next(self):
    with self._idx_lock:
      if not self._current_idx:
        periodic_update()
      idx = self._current_idx
      self._current_idx = (self._current_idx + 1) % len(self._list)
      return idx, self._list[idx]

  def load(self):
    proxy_scraper.load_proxies("proxy_list.txt")
    self._list = [ProxyInfo(item[0], item[1]) for item in proxy_scraper.result]
    proxy_scraper.clear()
    if not self._list:
      raise Exception("No proxies found!")
    random.shuffle(self._list)
    print(colors.OKCYAN[0] + f'Total proxies: {len(self._list)}' + colors.ENDC)
    global COOLDOWN_THRESHOLD
    if PROXY_RESERVE * proxy_thread_count < len(self._list):
      while True:
        good_count = sum((1 for proxy in self._list if not cooldowns.blocks(proxy.url, False)))
        if good_count > PROXY_RESERVE * proxy_thread_count:
          COOLDOWN_THRESHOLD /= 1.2
          break
        COOLDOWN_THRESHOLD *= 1.2
    else:
      good_count = len(self._list)
      COOLDOWN_THRESHOLD = float('inf')
    print(colors.OKCYAN[0] + f'Not blacklisted: {good_count}' + colors.ENDC)

  def get_hash(self):
    with open("proxy_list.txt", "rb") as f:
      return hashlib.md5(f.read()).hexdigest()

  def refresh(self):
    if self.get_hash() != self.hash:
      self.load()

  def check_proxies(self):
    while True:
      if terminated: return
      idx, proxy = self.next()
      identifier = f"Num {str(idx).rjust(4)} | {proxy.url.center(21)} | "
      if cooldowns.blocks(proxy.url):
        continue
      if terminated: return
      result = self.checker.check_proxy(proxy.url,
          checked_type = PROXY_CHECK_ORDER[proxy.type] if recheck_proxy else [proxy.type],
          check_country = False)
      if terminated: return
      if not result:
        cooldowns.add(proxy.url, BAD_PROXY_COOLDOWN)
        error_log(log_proxy_events, identifier + f"{proxy.type} --> Bad proxy")
        continue
      if filter_anonymity and not result.anonymity in filter_anonymity:
        cooldowns.add(proxy.url, BAD_ANON_COOLDOWN)
        error_log(log_proxy_events, identifier + f"{proxy.type} --> Bad anonymity: {result.anonymity}")
        continue
      if not proxy.type:
        proxy.type = result.protocols.pop()
      elif not proxy.type in result.protocols:
        error_log('persist', identifier + f"{proxy.type} --> Wrong protocol, actually {result.protocols}")
        proxy.type = result.protocols.pop()
      combined_log(log_proxy_events, (colors.OKGREEN, identifier + f"{proxy.type} --> Good Proxy"))
      if terminated: return
      while browser_count.value >= needed_browsers():
        time.sleep(over_limit_sleep)
        if terminated: return
      add_thread(f"Video viewer {idx}", view_thread, identifier, proxy)

################ BROWSER ################

def needed_browsers():
  return min(max_browsers, max(0, browser_ratio * (max_video_players - video_player_count.value) + video_player_count.value))

def get_driver(agent, proxy):
  service = selenium.webdriver.firefox.service.Service(log_path=get_null_path())
  options = selenium.webdriver.FirefoxOptions()
  options.headless = headless

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

  sizes = random.choice(VIEWPORT).split('x')
  options.set_preference("media.volume_scale", "0.001")
  options.set_preference("media.default_volume", "0.001")
  options.set_preference("toolkit.cosmeticAnimations.enabled", "false")
  options.set_preference("general.useragent.override", agent)
  options.set_preference("media.autoplay.default", 0)
  options.set_preference("browser.link.open_newwindow", 1)
  options.set_preference("browser.link.open_newwindow.restriction", 0)
  options.set_preference("browser.cache.disk.enable", "false")
  options.set_preference("browser.cache.disk_cache_ssl", "false")
  options.set_preference("browser.cache.memory.enable", "false")
  options.set_preference("browser.cache.offline.enable", "false")
  options.set_preference("browser.cache.insecure.enable", "false")
  options.set_preference("media.block-autoplay-until-in-foreground", "false")
  options.set_preference("media.peerconnection.enabled", "false")
  options.set_preference("privacy.resistfingerprinting", "true")
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
  options.set_preference("webgl.disabled", "false")
  options.set_preference("privacy.firstparty.isolate", "true")
  options.set_preference("security.ssl.enable_false_start", "false")
  #options.set_preference("security.ssl3.rsa_des_ede3_sha", "false")
  #options.set_preference("security.ssl.requrie_safe_negotiation", "true")
  #options.set_preference("security.tls.version.min", "3")
  #options.set_preference("security.tls.enable_0rtt_data", "false")
  options.accept_insecure_certs = True
  if firefox_path: options.binary = firefox_path
  driver = selenium.webdriver.Firefox(options=options, service=service)
  driver_list.append(driver)
  driver.set_window_size(sizes[0], sizes[1])
  return driver

def quit_driver(driver):
  driver_list.remove(driver)
  driver.quit()

################ VIDEO ROUTES ################

class RouteRecord:
  CONNECTION_FAILURE = 2
  TYPE_FAILURE = 1.2
  DATA_FAILURE = 1.1
  FAILURE = 1
  SUCCESS = 0
  def __init__(self, first_record_type, first_data=None):
    self.type_failures = [0, 0, 0]
    self.data_failures = {}
    self.add_record(first_record_type, first_data)
  def repr_tups(self):
    def format_record(record):
      msg = []
      if record[self.SUCCESS]:
        msg.append((colors.OKGREEN, f'S{record[self.SUCCESS]}'))
      if record[self.CONNECTION_FAILURE]:
        msg.append((colors.WARNING, f'C{record[self.CONNECTION_FAILURE]}'))
      if record[self.FAILURE]:
        msg.append((colors.FAIL, f'F{record[self.FAILURE]}'))
      return msg
    result = ['Route record: ', *format_record(self.type_failures)]
    for data, record in self.data_failures.items():
      result.append(f'\n  {data}: ')
      result += format_record(record)
    return result
  def add_record(self, record_type, data=None):
    if record_type == self.TYPE_FAILURE:
      self.type_failures[self.FAILURE] += 1
    elif record_type == self.CONNECTION_FAILURE:
      self.type_failures[self.CONNECTION_FAILURE] += 1
    else:
      if not data in self.data_failures:
        self.data_failures[data] = [0, 0, 0]
      if record_type == self.SUCCESS:
        self.type_failures[self.SUCCESS] += 1
        self.data_failures[data][self.SUCCESS] += 1
      elif record_type == self.DATA_FAILURE:
        self.data_failures[data][self.FAILURE] += 1

def type_keyword(driver, search_bar, keyword):
  search_bar = first_action_wrap(driver, EC.visibility_of_element_located(search_bar))
  bypass_consent(driver)
  for _ in range(3):
    try:
      search_bar.click()
      break
    except Exception:
      time.sleep(3)
  search_bar.clear()
  interval = random.weibullvariate(0.18, 1.7) + 0.04
  for letter in keyword:
    time.sleep(interval * random.weibullvariate(1.1, 4) if letter != ' ' else 0.2 + random.weibullvariate(0.4, 1.8))
    search_bar.send_keys(letter)
  time.sleep(interval * random.weibullvariate(0.9, 4))
  return search_bar

def make_video_finder(formatter, *popups):
  video_matchers = []
  for video in videos.targeted_videos:
    video_matchers.append((formatter(video.title), video))
    for alt in video.alt_titles:
      video_matchers.append((formatter(alt), video))
  def finder(driver):
    for matcher, video in video_matchers:
      try:
        video_element = driver.find_element(*matcher)
        if not video_element.is_displayed() or not video_element.is_enabled():
          continue
      except selenium.common.exceptions.NoSuchElementException:
        continue
      for selector in popups:
        for e in driver.find_elements(By.CSS_SELECTOR, selector):
          driver.execute_script("var element = arguments[0]; element.parentNode.removeChild(element);", e)
      for i in reversed(range(10)):
        try:
          driver.execute_script("arguments[0].scrollIntoView();", video_element)
          driver.execute_script(f'window.scrollBy(0, {random.uniform(-500, 0)});')
          time.sleep(random.uniform(0.5, 2))
          video_element.click()
          break
        except Exception as e:
          if not i:
            raise e
      return video
    time.sleep(random.uniform(0.5, 1.5))
  return finder

def bing_search(driver, keywords):
  first_page_wrap(driver, "https://www.bing.com")
  search_bar = type_keyword(driver, (By.CSS_SELECTOR, 'input#sb_form_q'), keywords)
  search_bar.send_keys(Keys.ENTER)
  WebDriverWait(driver, 30).until(EC.element_to_be_clickable((By.CSS_SELECTOR, "ol#b_results")))
  driver.find_element(By.CSS_SELECTOR, "li#b-scopeListItem-video").click()
  finder = make_video_finder(lambda title: (By.XPATH, f'//strong[text()="{title.replace("+", "")}"]'), "drv#stp_popup_tutorial")
  for i in range(10):
    time.sleep(random.uniform(1, 2))
    result = finder(driver)
    if result:
      while not "youtube.com" in driver.current_url:
        time.sleep(random.uniform(0.5, 1))
        try:
          WebDriverWait(driver, 30).until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'a.view_page'))).click()
        except Exception as e:
          if not "youtube.com" in driver.current_url:
            raise e
      return result
    driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.CONTROL, Keys.END)

def duck_search(driver, keywords):
  first_page_wrap(driver, "https://duckduckgo.com")
  if 'html' in driver.current_url:
    driver.get(f'https://duckduckgo.com/?q={keywords}&iax=videos&ia=videos')
  else:
    search_bar = type_keyword(driver, (By.CSS_SELECTOR, 'input#search_form_input_homepage'), keywords)
    search_bar.send_keys(Keys.ENTER)
    WebDriverWait(driver, 30).until(EC.element_to_be_clickable(
      (By.CSS_SELECTOR, "div#links.results")))
    time.sleep(random.uniform(0.5, 1))
    driver.find_element(By.XPATH, "//*[@data-zci-link='videos']").click()
  for e in driver.find_elements(By.CSS_SELECTOR, "span.js-badge-link-dismiss"):
    try:
      e.click()
    except Exception: pass
  finder = make_video_finder(lambda title: (By.XPATH, f'//a[text()="{title}"]'))
  for i in range(10):
    time.sleep(random.uniform(1, 2))
    try:
      driver.find_element(By.XPATH, "//*[@data-zci-link='videos']").click()
    except Exception: pass
    result = finder(driver)
    if result:
      try:
        WebDriverWait(driver, 30).until(EC.element_to_be_clickable((By.CSS_SELECTOR, 'a.js-video-privacy-leave'))).click()
      except Exception as e:
        if not 'youtube.com' in driver.current_url:
          raise e
      return result
    driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.CONTROL, Keys.END)

def yt_search(driver, keywords):
  spoof_referer(driver, random.choice(SEARCH_ENGINES), "https://www.youtube.com/")
  time.sleep(5)
  bypass_unsupported_browser(driver)
  try:
    search_bar = type_keyword(driver, (By.CSS_SELECTOR, 'input#search'), keywords)
  except FirstActionError:
    bypass_unsupported_browser(driver)
    search_bar = type_keyword(driver, (By.CSS_SELECTOR, 'input#search'), keywords)
  for _ in range(20):
    if random.randrange(2):
      search_bar.send_keys(Keys.ENTER)
    else:
      try:
        driver.find_element(By.XPATH, '//*[@id="search-icon-legacy"]').click()
      except Exception:
        driver.execute_script('document.querySelector("#search-icon-legacy").click()')
    if 'www.youtube.com/results' in driver.current_url:
      break
  finder = make_video_finder(lambda title: (By.XPATH, f'//a[@id="video-title" and @title="{title}"]'))
  for i in range(10):
    try:
      container = WebDriverWait(driver, 3).until(EC.visibility_of_element_located(
        (By.XPATH, f'//ytd-item-section-renderer[{i}]')))
    except selenium.common.exceptions.TimeoutException:
      container = driver
    result = finder(driver)
    if result:
      return result
    time.sleep(random.uniform(0.5, 1.5))
    driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.CONTROL, Keys.END)

def find_video_suggestion(driver):
  finder = make_video_finder(lambda title: (By.XPATH, f'//span[@id="video-title" and @title="{title}"]'))
  for i in range(10):
    result = finder(driver)
    if result:
      return result
    time.sleep(random.uniform(0.5, 1.5))
    if not driver.find_elements(By.CSS_SELECTOR, 'ytd-continuation-item-renderer'):
      break
    WebDriverWait(driver, 30).until(EC.visibility_of_element_located(
      (By.TAG_NAME, 'body'))).send_keys(Keys.CONTROL, Keys.END)

################ VIDEOS ################

class Video:
  def __init__(self, id, info, fake_watch):
    self.id = id
    self.title = info['title']
    self.alt_titles = info.get('alt_titles', [])
    self.fake_watch = fake_watch
    self.routes = []
    for type, arr in info['routes'].items():
      self.routes += [(type, data) for data in arr ] * (search_preference if 'search' in type else 1)
    for link in get_fallback_links(self.id):
      self.routes.append(('url', link))
      #self.routes.append(('url', GOOGLE_LINK_TEMPLATE.format(url=link)))
  def open(self, identifier, driver):
    while True:
      route = random.choice(self.routes)
      try:
        if 'search' in route[0]:
          if route[0] == 'bing_search':
            result = bing_search(driver, route[1])
          elif route[0] == 'duck_search':
            result = duck_search(driver, route[1])
          elif route[0] == 'yt_search':
            result = yt_search(driver, route[1])
          else:
            raise Exception(f"Invalid route type: {route[0]}")
          if result:
            wait_for_video(driver)
            bypass_consent(driver)
            videos.add_route_record(route[0], RouteRecord.SUCCESS, route[1])
            return
          error_log('persist', identifier + f"{route[0]} failed: {route[1]} :::: {self.title}. Fallback to url")
          videos.add_route_record(route[0], RouteRecord.DATA_FAILURE, route[1])
        elif route[0] == 'url':
          spoof_referer(driver, random.choice(REFERERS), route[1])
          bypass_unsupported_browser(driver)
          wait_for_video(driver)
          bypass_consent(driver)
          videos.add_route_record(route[0], RouteRecord.SUCCESS, route[1])
          return
        else:
          raise Exception("Invalid route type: " + route[0])
      except Exception as e:
        if isinstance(e, LoadingError):
          videos.add_route_record(route[0], RouteRecord.CONNECTION_FAILURE)
          raise e
        else:
          take_screenshot(driver)
          videos.add_route_record(route[0], RouteRecord.TYPE_FAILURE)
          error_log('persist', identifier + f"Error during {route[0]}: {traceback.format_exc()}")

class Videos:
  def __init__(self):
    self.targeted_videos, self.all_videos = self.load()
    self.hash = self.get_hash()
    self.route_records = {}
  @staticmethod
  def load():
    with open('videos.json', 'r', encoding='utf-8') as fp:
      video_dict = json.load(fp)
    if not video_dict:
      error_log('persist', f"Your videos.json is empty!")
      sys.exit()
    targeted_videos = [Video(id, info, False) for id, info in video_dict.items()]
    print(colors.OKGREEN[0] + f'{len(targeted_videos)} videos loaded' + colors.ENDC)
    if os.path.isfile('fake_watch_videos.json'):
      with open('fake_watch_videos.json', 'r', encoding='utf-8') as fp:
        all_videos = targeted_videos + [Video(id, info, True) for id, info in json.load(fp).items()]*jumping_video_preference
    else:
      all_videos = targeted_videos
    return targeted_videos, all_videos
  def get_hash(self):
    hash = hashlib.md5()
    with open("videos.json", "rb") as f:
      hash.update(f.read())
    if os.path.isfile('fake_watch_videos.json'):
      with open("fake_watch_videos.json", "rb") as f:
        hash.update(f.read())
    return hash.hexdigest()
  def detect_changes(self):
    new_hash = self.get_hash()
    if new_hash != self.hash:
      combined_log('temp', "Reloading videos...")
      try:
        self.targeted_videos, self.all_videos = self.load()
        self.hash = new_hash
      except:
        combined_log('persist', (colors.FAIL, traceback.format_exc()))
  def add_route_record(self, route_type, record_type, route_data=None):
    if not route_type in self.route_records:
      self.route_records[route_type] = RouteRecord(record_type, route_data)
    else:
      self.route_records[route_type].add_record(record_type, route_data)

################ BYPASSES ################

accept_texts = ("j'accepte", "i agree", "jag godkänner", "ich stimme zu", "acepto", "accepto", "accetto", "aceito", "ak stem in", "jeg accepterer", "nõustun", "souhlasím", "ik ga akkoord", "принимаю", "saya setuju", "hyväksyn", "ຂ້າພະເຈົ້າຍອມຮັບ", "我同意")
accept_texts_lower = ''.join(set(''.join(accept_texts).lower()) - {"'", '"'})
accept_texts_upper = accept_texts_lower.upper()
def bypass_consent(driver):
  for i in range(50):
    try:
      for text in accept_texts:
        consent = driver.find_elements(By.XPATH, f'//*[translate(., "{accept_texts_upper}", "{accept_texts_lower}")="{text}"]')
        if consent:
          consent = consent[0]
          break
      else:
        return i
      driver.execute_script("arguments[0].scrollIntoView();", consent)
      time.sleep(random.uniform(0.5, 1))
      consent.click()
    except (selenium.common.exceptions.ElementNotVisibleException, selenium.common.exceptions.ElementNotInteractableException) as e:
      combined_log(log_regular_errors, f"Bypass consent error: {repr(e)}")
      return i
  else:
    raise Exception("Consent form still visible after 50 tries")

def bypass_unsupported_browser(driver):
  time.sleep(random.uniform(1, 2))
  while 'www.youtube.com/supported_browsers' in driver.current_url:
    try:
      driver.find_element(By.CSS_SELECTOR, "a#return-to-youtube").click()
    except Exception:
      combined_log('persist', (colors.FAIL, traceback.format_exc()))
    time.sleep(random.uniform(0.1, 1))

def bypass_signin(driver):
  for _ in range(10):
    time.sleep(2)
    try:
      nothanks = driver.find_element(By.CLASS_NAME,
        "style-scope.yt-button-renderer.style-text.size-small")
      nothanks.click()
      time.sleep(1)
      driver.switch_to.frame(driver.find_element(By.ID, "iframe"))
      iagree = driver.find_element(By.ID, 'introAgreeButton')
      iagree.click()
      driver.switch_to.default_content()
    except Exception:
      try:
        driver.switch_to.frame(driver.find_element(By.ID, "iframe"))
        iagree = driver.find_element(By.ID, 'introAgreeButton')
        iagree.click()
        driver.switch_to.default_content()
      except Exception:
        pass

def bypass_other_popups(driver):
  labels = ['Got it', 'Skip trial', 'No thanks', 'Dismiss', 'Not now']
  random.shuffle(labels)
  for label in labels:
    try:
      driver.find_element(By.XPATH, f"//*[@id='button' and @aria-label='{label}']").click()
    except Exception:
      pass

def skip_stuff(identifier, driver):
  try:
    WebDriverWait(driver, 15).until(EC.element_to_be_clickable(
      (By.CLASS_NAME, "ytp-ad-preview-container")))
  except Exception:
    combined_log(log_regular_events, identifier + "No ads found")
  else:
    try:
      combined_log(log_regular_events, identifier + "Skipping Ads...")
      skip_button = WebDriverWait(driver, 20).until(EC.element_to_be_clickable(
          (By.CLASS_NAME, "ytp-ad-skip-button")))
      time.sleep(random.uniform(0.1, 5))
      skip_button.click()
    except Exception as e:
      combined_log(log_regular_errors, identifier + f"Ad skipping exception: {repr(e)}")
  bypass_other_popups(driver)

################ PLAYING ################

def check_title(driver):
  for video in videos.targeted_videos:
    if video.title in driver.title: return True
    for alt in video.alt_titles:
      if alt in driver.title: return True

def play_video(driver, check=True):
  if check and not check_title(driver):
    raise Exception(f"Watching wrong video: {driver.title}")
  try:
    try:
      driver.find_element(By.CLASS_NAME, 'ytp-ad-skip-button').click()
    except selenium.common.exceptions.NoSuchElementException:
      pass
    driver.find_element_by_css_selector(By.CSS_SELECTOR, '[title^="Pause (k)"]')
  except Exception:
    try:
      driver.find_element_by_css_selector(By.CSS_SELECTOR, '[title^="Play (k)"]').click()
    except Exception:
      pass

def play_music(driver, check=True):
  if check and not check_title(driver):
    raise Exception(f"Watching wrong video: {driver.title}")
  try:
    try:
      driver.find_element(By.CLASS_NAME, 'ytp-ad-skip-button').click()
    except selenium.common.exceptions.NoSuchElementException:
      pass
    driver.find_element(By.XPATH, '//*[@id="play-pause-button" and @title="Pause"]')
  except Exception:
    try:
      driver.find_element(By.XPATH, '//*[@id="play-pause-button" and @title="Play"]').click()
    except Exception:
      driver.execute_script(
        'document.querySelector("#play-pause-button").click()')

def play(identifier, cooldown_url, driver, title, fake_watch = False):
  bypass_consent(driver)
  skip_stuff(identifier, driver)
  if "music.youtube.com" in driver.current_url:
    content_type = 'Music'
    play_music(driver, False)
    view_stat = 'Music'
  else:
    content_type = 'Video'
    play_video(driver, False)
    if save_bandwidth:
      reduce_bandwidth(driver)
    change_playback_speed(driver)
    try:
      view_stat = WebDriverWait(driver, 30).until(EC.visibility_of_element_located(
        (By.XPATH, '//span[@class="view-count style-scope ytd-video-view-count-renderer"]'))).text
    except Exception as e:
      error_log(log_regular_errors, identifier + f"Can't find video stat: {repr(e)}")
      view_stat = "0 views"

  view_accounted = False
  if fake_watch:
    time.sleep(random.uniform(5, 10))
  elif 'watching' in view_stat:
    error = 0
    while True:
      if terminated:
        raise TerminatedError()
      view_stat = driver.find_element(By.XPATH,
        '//span[@class="view-count style-scope ytd-video-view-count-renderer"]').text
      if 'watching' in view_stat:
        combined_log(log_regular_events, identifier + "Stream found, {view_stat} ")
      else:
        error += 1
      random_command(identifier, driver)
      play_video(driver)
      if error == 5:
        break
      time.sleep(60)
      watch_time.increment(60/3600)
      if not view_accounted:
        views.increment()
        view_accounted = True
  else:
    try:
      current_url = driver.current_url
      video_len = 0
      while video_len == 0:
        video_len = driver.execute_script(
          "return document.getElementById('movie_player').getDuration()")
      video_len = video_len*random.uniform(minimum, maximum)

      duration = str(datetime.timedelta(seconds=video_len))
      combined_log(log_regular_events, identifier + f"{content_type} found, Watch Duration : {duration} ")
    except Exception:
      error_log('persist', identifier + "Suppressed exception before playing: {traceback.format_exc()}")

    prev_time = 0
    for _ in range(round(video_len/2)):
      if terminated:
        raise TerminatedError()
      time.sleep(random.uniform(20, 30))
      if not view_accounted:
        views.increment()
        view_accounted = True
      current_time = driver.execute_script("return document.getElementById('movie_player').getCurrentTime()")
      watch_time.increment((current_time - prev_time)/3600)
      prev_time = current_time
      if content_type == 'Video':
        random_command(identifier, driver)
        play_video(driver)
      elif content_type == 'Music':
        play_music(driver)
      if current_time > video_len or driver.current_url != current_url:
        break
  if random.randrange(2):
    movie_player = driver.find_element(By.ID, 'movie_player')
    driver.execute_script("arguments[0].scrollIntoView();", movie_player)
    movie_player.send_keys('k')
  cooldowns.add(cooldown_url, WATCH_COOLDOWN)

available_qualities = ('360p', '480p', '720p', '1080p')
def reduce_bandwidth(driver):
  try:
    driver.find_element(By.CSS_SELECTOR, "button.ytp-button.ytp-settings-button").click()
    driver.find_element(By.XPATH, "//span[text()={available_qualities}]").click()
    random_quality = random.choice(['144p', '240p', '360p'])
    quality = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, f"//span[contains(string(),'{random_quality}')]")))
    driver.execute_script("arguments[0].scrollIntoView();", quality)
    quality.click()
  except Exception:
    try:
      driver.find_element(By.XPATH,
        '//*[@id="container"]/h1/yt-formatted-string').click()
    except Exception:
      pass

def change_playback_speed(driver):
  if playback_speed == 2:
    driver.find_element(By.ID, 'movie_player').send_keys('<'*(random.randrange(3) + 1))
  elif playback_speed == 3:
    driver.find_element(By.ID, 'movie_player').send_keys('>'*(random.randrange(3) + 1))

#COMMANDS = [Keys.UP, Keys.DOWN, 'k', 'j', 'l', 't', 'c']
COMMANDS = [Keys.UP, Keys.DOWN, 'k', 'j', 'l', 't', 'c']
def random_command(identifier, driver):
  try:
    bypass_other_popups(driver)
    option = random.choices([1, 2], cum_weights=(0.7, 1.00), k=1)[0]
    if option == 2:
      movie_player = driver.find_element(By.ID, 'movie_player')
      driver.execute_script("arguments[0].scrollIntoView();", movie_player)
      command = random.choice(COMMANDS)
      if command in {'m', 't', 'c'}:
        movie_player.send_keys(command)
      #elif command == 'k':
      #  press = random.randrange(2)
      #  if press:
      #    movie_player.send_keys(command)
      #  for _ in range(2, 5):
      #    driver.execute_script(f'window.scrollBy(0, {random.uniform(300, 700)});')
      #    time.sleep(random.uniform(0.5, 3))
      #  driver.execute_script("arguments[0].scrollIntoView();", movie_player)
      #  if press:
      #    movie_player.send_keys(command)
      else:
        movie_player.send_keys(command*(random.randrange(5)+1))
  except Exception:
    if not bypass_consent(driver):
      take_screenshot(driver)
      error_log('persist', identifier + f"Random command error: {traceback.format_exc()}")

################ VIEW THREAD ################

def view_thread(identifier, proxy):
  browser_count.increment()
  try:
    combined_log(log_proxy_events, (colors.OKGREEN, identifier + "Opening a driver..."))
    driver = get_driver(useragents.random, proxy)
    try:
      for _ in range(4):
        current = random.choice(videos.all_videos)
        current.open(identifier, driver)
        if video_player_count.value < max_video_players:
          try:
            video_player_count.increment()
            play(identifier, proxy.url, driver, current.title, current.fake_watch)
            for idx in range(random.randint(3, 5)):
              next = find_video_suggestion(driver)
              if not next:
                error_log('persist', identifier + f"Can't find a recommended video from {current.title}, opening a new one")
                current = random.choice(videos.targeted_videos)
                current.open(identifier, driver)
              else:
                combined_log(log_regular_events, identifier + f"Jumped '{current.title}' --> '{next.title}'")
                current = next
              play(identifier, proxy.url, driver, current.title, current.fake_watch)
          finally:
            video_player_count.increment(-1)
        else:
          combined_log(log_reached_limit, identifier + f"Reached video player limit")
          time.sleep(over_limit_sleep)
          break
      combined_log(log_regular_events, identifier + "Closing video player")
    except (FirstPageError, FirstActionError, LoadingError) as e:
      cooldowns.add(proxy.url, SLOW_PROXY_COOLDOWN)
      error_log(log_regular_errors, identifier + f"{type(e).__name__}! Slow internet or stuck at recaptcha")
      return
    except selenium.common.exceptions.WebDriverException:
      take_screenshot(driver)
      cooldowns.add(proxy.url, SLOW_PROXY_COOLDOWN)
      error_log(log_regular_errors, identifier + f"WebDriverException: {traceback.format_exc()}")
      return
    except Exception:
      take_screenshot(driver)
      error_log('persist', identifier + f"Watch loop exception : {traceback.format_exc()}")
    finally:
      quit_driver(driver)
  except TerminatedError:
    print(f"{identifier}terminated")
  except Exception:
    error_log('persist', identifier + f"Main viewer : {traceback.format_exc()}")
  finally:
    browser_count.increment(-1)

################ COMMAND LINE ################

def print_view_records():
  combined_log('persist', f'Views: {views.value - og_views}')
  watch_hours = watch_time.value - og_watch_time
  ratio = watch_hours / (time.time() - start_time)*3600
  combined_log('persist', f'Hours: {watch_hours}')
  combined_log('persist', f'Watch hour / real hour = {ratio}')
  combined_log('persist', f'Efficiency = {ratio / max_video_players}')
def print_route_records():
  if videos.route_records:
    combined_log('persist', (colors.OKGREEN, 'S: success'), (colors.WARNING, 'C: connection failure'), (colors.FAIL, 'F: other failure'))
    for type, record in list(videos.route_records.items()):
      combined_log('persist', f'{type}: ', *record.repr_tups())
  else:
    combined_log('persist', 'No Data')

def process_cmd(cmd):
  cmd = cmd.lower()
  global max_video_players
  global detailed_proxy_errors
  if cmd in {'player_status', 'players', 'player', 'p'}:
    print(f"Browser count: {browser_count.value}")
    print(f"Video player count: {video_player_count.value}/{max_video_players}")
  elif cmd[1:] in {'player', 'players', 'p'}:
    if cmd[0] == '+':
      max_video_players += 1
    elif cmd[0] == '-':
      max_video_players -= 1
    elif cmd[0] == '0':
      max_video_players = 0
    else:
      print("Invalid operator: {cmd[0]}")
    print(f"Max video players: {max_video_players}")
  elif cmd[1:] in {'proxy errors', 'proxy_errors', 'pe'}:
    detailed_proxy_errors = cmd[0] == '+'
  elif cmd in {'route_records', 'records', 'r'}:
    print_route_records()
  elif cmd in {'view_stats', 'views', 'v'}:
    print_view_records()
  elif cmd:
    print(f"Invalid command: {cmd}")

################ MAIN ################

def periodic_update():
  proxies.refresh()
  random.shuffle(videos.targeted_videos)
  random.shuffle(videos.all_videos)

def main():
  print(
  colors.FAIL[0]+r"                     ,----,"+colors.OKBLUE[0]+"                               ,----,\n" +
  colors.FAIL[0]+r"                   ,'   .:|"+colors.OKBLUE[0]+"                             ,'   .:|\n" +
  colors.FAIL[0]+r"                 ,`   .::::"+colors.OKBLUE[0]+"  ,---,       ,---,,       ,`   .::::\n" +
  colors.FAIL[0]+r"         ,----,,'   ,::::,'"+colors.OKBLUE[0]+",'  .::\    ,`  ,::::,   ,'   ,::::,'\n" +
  colors.FAIL[0]+r"        /__,;:'___,:::::|"+colors.OKBLUE[0]+",---,':_:::  /   /::::::;.'___,:::::|  \n" +
  colors.FAIL[0]+r" ,---,  | |::|    |:::::|"+colors.OKBLUE[0]+"|   |:| |:: /   /::::::::\    ::::::|  \n" +
  colors.FAIL[0]+r":___/:\;  |::|    |:'|::|"+colors.OKBLUE[0]+"|   |:|/:/ ;   ;:::/  \:::;   |:'|::|  \n" +
  colors.FAIL[0]+r" \  \::\ ,'::;----'  |::|"+colors.OKBLUE[0]+"|   |:::.  ;   |::;',  ;::|---'  |::|  \n" +
  colors.FAIL[0]+r"  \  \::\'::|    |   |::|"+colors.OKBLUE[0]+"|   |::::\ |   |::| |  |::|  |   |::|  \n" +
  colors.FAIL[0]+r"   \  \:::::;    |   |::|"+colors.OKBLUE[0]+"|   |::_:::.   |::| |  |::|  |   |::|  \n" +
  colors.FAIL[0]+r"    ', ',::|     |   |::|"+colors.OKBLUE[0]+"|   |:| |:|'   ;::;/   ;::;  |   |::|  \n" +
  colors.FAIL[0]+r"     ;  ;::;     |   |.' "+colors.OKBLUE[0]+"|   |:|/::: \   \::',,':::   |   |:'   \n" +
  colors.FAIL[0]+r"    |  |::|      '---'   "+colors.OKBLUE[0]+"|   |:::,'   ;   :::::::;    '---'     \n" +
  colors.FAIL[0]+r"    ;  ;::;              "+colors.OKBLUE[0]+"|   |::'      `,  `::::`               \n" +
  colors.FAIL[0]+r"     `---`               "+colors.OKBLUE[0]+"`----'          `---``                 \n" +
  colors.ENDC)
  global terminated
  global add_thread

  def thread_wrapper(msg, func, *args):
    try:
      func(*args)
    except Exception:
      error_log('persist', f"{msg} error: {traceback.format_exc()}")
    if terminated:
      print(f"{msg} exited")

  def add_thread(msg, func, *args):
    thread = threading.Thread(target=thread_wrapper, args=(msg, func, *args))
    thread.start()
    return thread
  add_thread("Database udpate", update_database)
  webserver_thread = web_interface and add_thread("Web server", website.start_server, host, port)
  while not cooldowns:
    time.sleep(0.1)
  for _ in range(proxy_thread_count):
    add_thread("Proxy checker", proxies.check_proxies)
  try:
    while True:
      try:
        process_cmd(input())
      except Exception:
        error_log('persist', f"CLI error: {traceback.format_exc()}")
  except KeyboardInterrupt:
    try:
      print_route_records()
      print_view_records()
      terminated = True
      print()
      print("Stopping subprocesses... please wait")
      if webserver_thread and webserver_thread.is_alive():
        requests.post(f'http://{host}:{port}/shutdown')
      for driver in driver_list:
        driver.quit()
    except Exception:
      combined_log('persist', (colors.FAIL, traceback.format_exc()))
    finally:
      sys.exit()
  except Exception:
    combined_log('persist', (colors.FAIL, traceback.format_exc()))

if __name__ == '__main__':
  for _ in range(9):
    try:
      useragents = fake_useragent.UserAgent()
      break
    except Exception: pass
  else:
    useragents = fake_useragent.UserAgent()

  default_settings = {
    "web_interface": {
      "enabled": True,
      "host": "0.0.0.0",
      "port": 5000
    },
    "headless": False,
    "firefox_path": None,
    "filter_anonymity": None,
    "minimum_percent": 70.0,
    "maximum_percent": 90.0,
    "save_bandwidth": True,
    "playback_speed": 1,
    "proxy_thread_count": 40,
    "browser_per_video_player": 3,
    "video_player_count": 5,
    "max_browsers": 15,
    "jumping_video_preference": 1,
    "search_preference": 2,
    "log_file": "ytbot.log",
  }
  #if not os.path.isfile('config.json'):
  #  create_config()
  with open('config.json', 'r') as openfile:
    config = json.load(openfile)
  config = {**default_settings, **config}

  web_interface = config["web_interface"]["enabled"]
  host = config["web_interface"]["host"]
  port = config["web_interface"]["port"]
  jumping_video_preference = config["jumping_video_preference"]
  search_preference = config["search_preference"]
  headless = config["headless"]
  filter_anonymity = config["filter_anonymity"]
  firefox_path = config["firefox_path"]
  minimum = config["minimum_percent"] / 100
  maximum = config["maximum_percent"] / 100
  save_bandwidth = config["save_bandwidth"]
  playback_speed = config["playback_speed"]
  proxy_thread_count = config["proxy_thread_count"]
  browser_ratio = config["browser_per_video_player"]
  max_video_players = config["video_player_count"]
  max_browsers = config["max_browsers"]
  cooldowns = None

  log_file = open(config["log_file"], 'w') if config.get("log_file") else None
  try:
    driver_list = []
    recheck_proxy = True
    over_limit_sleep = 10
    browser_count = AtomicCounter()
    video_player_count = AtomicCounter()
    terminated = False
    over_limit_sleep = proxy_thread_count*OVER_LIMIT_SLEEP_UNIT

    videos = Videos()
    proxies = Proxies()

    main()
  finally:
    if log_file:
      log_file.close()
