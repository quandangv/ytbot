import hashlib
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
import proxy_checker
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

import website
from config import create_config

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

driver_list = []
view = []
checked = {}
console = []
threads = 0
recheck_proxy = True
over_limit_sleep = 10
browser_count = AtomicCounter()
video_player_count = AtomicCounter()

terminated = False
detailed_proxy_errors = True
log_reached_limit = False
log_proxy_events = 'console'
log_regular_events = 'console'
log_regular_errors = 'console'

COOLDOWN_PER_HOUR = 1
COOLDOWN_THRESHOLD = 2
MIN_COOLDOWN = 0.1
BAD_PROXY_COOLDOWN = 2
SLOW_PROXY_COOLDOWN = 1
BAD_ANON_COOLDOWN = 48
WATCH_COOLDOWN = 12
OVER_LIMIT_SLEEP_UNIT = 4
VIEW_THREAD_RESERVE = 4

STAT_DATABASE = 'stats.db'
COOLDOWN_DATABASE = 'proxy_cooldowns.db'

VIEWPORT = ['2560x1440', '1920x1080', '1440x900', '1536x864', '1366x768', '1280x1024', '1024x768']

SEARCH_ENGINES = ['https://search.yahoo.com/', 'https://duckduckgo.com/', 'https://www.google.com/',
      'https://www.bing.com/', '', '']
REFERERS = SEARCH_ENGINES + ['https://t.co/']

GOOGLE_LINK_TEMPLATE = "https://www.google.com/url?sa=t&rct=j&q=&esrc=s&source=video&cd=&url={url}"
YOUTUBE_LINK_TEMPLATE = "https://www.youtube.com/watch?v={id}"
YOUTU_BE_LINK_TEMPLATE = "https://youtu.be/{id}"

COMMANDS = [Keys.UP, Keys.DOWN, 'k', 'j', 'l', 't', 'c']

website.console = console
website.database = STAT_DATABASE

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

today = str(datetime.datetime.today().date())
def init_database():
  global watch_time
  global og_watch_time
  global views
  global og_views
  cursor = stats_db.cursor()
  cursor.execute("CREATE TABLE IF NOT EXISTS statistics (date TEXT, hours REAL, views INTEGER)")
  try:
    cursor.execute("SELECT hours, views FROM statistics WHERE date = ?", (today,))
    watch_time = AtomicCounter(cursor.fetchone()[0])
    views = AtomicCounter(cursor.fetchone()[1])
  except Exception:
    cursor.execute("INSERT INTO statistics VALUES (?, ?, ?)", (today, 0, 0))
    watch_time = AtomicCounter(0)
    views = AtomicCounter(0)
  og_watch_time = watch_time.value
  og_views = views.value
  stats_db.commit()

list_wrap = lambda item: item if isinstance(item, list) else [item]

proxy_check_order = {
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
    self._current_idx= 0
    self._idx_lock = threading.Lock()
    self.checker = proxy_checker.Checker()

  def driver(self):
    if self._driver:
      return self._driver
    service = selenium.webdriver.firefox.service.Service(log_path=get_null_path())
    options = selenium.webdriver.FirefoxOptions()
    options.accept_insecure_certs = True
    options.headless = True
    if firefox_path:
      options.binary = firefox_path
    self._driver = selenium.webdriver.Firefox(options=options, service=service)
    driver_list.append(self._driver)
    return self._driver

  def next(self):
    with self._idx_lock:
      if not self._current_idx:
        periodic_update()
      idx = self._current_idx
      self._current_idx = (self._current_idx + 1) % len(self._list)
      return idx, self._list[idx]

  def refresh(self):
    self._list = []
    self._urls = set()
    self._gather()
    if os.path.isfile('proxies.pyx'):
      with open('proxies.pyx', 'r') as openfile:
        # pyx is for Python Expression
        sources = eval(openfile.read())
    else:
      print(colors.FAIL[0] + "No proxies.pyx found!")
    for source in list_wrap(sources):
      self._load(source)
    self._urls = None
    if not self._list:
      raise Exception("No proxies found!")
    random.shuffle(self._list)
    print(colors.OKCYAN[0] + f'Total proxies: {len(self._list)}' + colors.ENDC)
    global COOLDOWN_THRESHOLD
    if VIEW_THREAD_RESERVE * proxy_thread_count < len(self._list):
      while True:
        good_count = sum((1 for proxy in self._list if not cooldowns.blocks(proxy.url, False)))
        if good_count > VIEW_THREAD_RESERVE * proxy_thread_count:
          COOLDOWN_THRESHOLD /= 1.2
          break
        COOLDOWN_THRESHOLD *= 1.2
    else:
      good_count = len(self._list)
      COOLDOWN_THRESHOLD = float('inf')
    print(colors.OKCYAN[0] + f'Not blacklisted: {good_count}' + colors.ENDC)

  def _load(self, source):
    def add_list(url, type):
      if not url in self._urls:
        self._urls.add(url)
        self._list.append(ProxyInfo(type, url))
    extract_type = lambda source: source if isinstance(source, tuple) else (source, None)
    if isinstance(source, dict):
      if isinstance(source['regex'], str):
        source['regex'] = re.compile(source['regex'], re.DOTALL)
        if source['regex'].groups != 2:
          raise Exception("Proxy regex must contain 2 groups (for host and port)")
      for url in list_wrap(source['url']):
        if isinstance(url, dict):
          # Selenium doesn't support complicated requests, so we use requests
          real_url, type = extract_type(url['url'])
          response = requests.request(url.get('method', 'GET'), real_url,
              data=url.get('data', None),
              headers={"User-Agent": useragents.random})
          if 'javascript' in url:
            htmlb64 = base64.b64encode(response.text.encode('utf-8')).decode()
            raw = self.driver().get('data:text/html;base64,' + htmlb64).page_source
            self.driver().get('about:blank')
          else:
            raw = response.text
        else:
          url, type = extract_type(url)
          raw = requests.get(url, headers={"User-Agent": useragents.random}).text
        for host, port in source['regex'].findall(raw):
          add_list(f'{host}:{port}', type)
      return
    source, type = extract_type(source)
    def add_line(line):
      if line:
        if line.count(':') == 3:
          split = line.split(':')
          line = f'{split[2]}:{split[-1]}@{split[0]}:{split[1]}'
        add_list(line, type)
    if source.startswith('http://') or source.startswith('https://'):
      lines = requests.get(source).text
      for line in lines.split('\r\n' if '\r\n' in lines else '\n'):
        add_line(line)
    else:
      with open(source, encoding="utf-8") as fh:
        for line in fh:
          add_line(line.strip())

  def _gather(self):
    self._load(('https://raw.githubusercontent.com/clarketm/proxy-list/master/proxy-list-raw.txt', None))
    self._load(('https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt', 'http'))
    self._load(('https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/socks4.txt', 'socks4'))
    self._load(('https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/socks5.txt', 'socks5'))
    self._load(('https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/proxy.txt', None))
    self._load(('https://raw.githubusercontent.com/sunny9577/proxy-scraper/master/proxies.txt', None))

  def check_proxies(self):
    while True:
      if terminated: return
      idx, proxy = self.next()
      identifier = f"Num {str(idx).rjust(4)} | {proxy.url.center(21)} | "
      if cooldowns.blocks(proxy.url):
        continue
      if terminated: return
      result = self.checker.check_proxy(proxy.url,
          checked_type = proxy_check_order[proxy.type] if recheck_proxy else [proxy.type],
          check_country = False)
      if terminated: return
      if not result:
        cooldowns.add(proxy.url, BAD_PROXY_COOLDOWN)
        combined_log(log_proxy_events, (colors.FAIL, identifier + f"{proxy.type} --> Bad proxy"))
        continue
      if filter_anonymity and not result.anonymity in filter_anonymity:
        cooldowns.add(proxy.url, BAD_ANON_COOLDOWN)
        combined_log(log_proxy_events, (colors.FAIL, identifier + f"{proxy.type} --> Bad anonymity: {result.anonymity}"))
        continue
      if not proxy.type:
        proxy.type = result.protocols.pop()
      elif not proxy.type in result.protocols:
        combined_log('html', (colors.FAIL, identifier + f"{proxy.type} --> Wrong protocol, actually {result.protocols}"))
        proxy.type = result.protocols.pop()
      combined_log(log_proxy_events, (colors.OKGREEN, identifier + f"{proxy.type} --> Good Proxy"))
      if terminated: return
      while browser_count.value >= needed_browsers():
        time.sleep(over_limit_sleep)
        if terminated: return
      add_thread(f"Video viewer {idx}", view_thread, identifier, proxy)

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

def combined_log(level, *text_tups):
  if level and not terminated:
    timestamp = datetime.datetime.now().strftime("[%d-%b-%Y %H:%M:%S] ")
    text_tups = [(colors.NONE, timestamp), *text_tups]
    print(''.join([color[0] + msg for color, msg in text_tups]) + colors.ENDC)
    if api and level == 'html':
      if len(console) > 50:
        console.pop(0)
      html = ''.join([f'<span style="color:{key[1]}"> {value} </span>' for key, value in text_tups])
      console.append(html)

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
  def __str__(self):
    format_record = lambda record: f'S{record[self.SUCCESS]}-C{record[self.CONNECTION_FAILURE]}-F{record[self.FAILURE]}'
    data_str = ', '.join(f'{data}: {format_record(ratio)}' for data, ratio in self.data_failures.items())
    return f'RouteRecord({format_record(self.type_failures)}, {{{data_str}}})'
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

class Video:
  def __init__(self, id, info, fake_watch):
    self.id = id
    self.title = info['title']
    self.alt_titles = info.get('alt_titles', [])
    self.fake_watch = fake_watch
    self.routes = []
    for type, arr in info['routes'].items():
      self.routes += [(type, data) for data in arr ] * (search_boost if 'search' in type else 1)
    for link in get_fallback_links(self.id):
      self.routes.append(('url', link))
      #self.routes.append(('url', GOOGLE_LINK_TEMPLATE.format(url=link)))
  def open(self, identifier, driver):
    while True:
      route = random.choice(self.routes)
      if 'search' in route[0]:
        try:
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
        except Exception as e:
          if isinstance(e, LoadingError):
            videos.add_route_record(route[0], RouteRecord.CONNECTION_FAILURE)
            raise e
          else:
            videos.add_route_record(route[0], RouteRecord.TYPE_FAILURE)
            combined_log('html', (colors.FAIL, identifier + f"Error during {route[0]}: {traceback.format_exc()}"))
        else:
          combined_log('html', (colors.FAIL, identifier + f"{route[0]} failed: {route[1]} :::: {self.title}. Fallback to url"))
          videos.add_route_record(route[0], RouteRecord.DATA_FAILURE, route[1])
        continue
      if route[0] == 'url':
        try:
          spoof_referer(driver, random.choice(REFERERS), route[1])
          bypass_unsupported_browser(driver)
          wait_for_video(driver)
          bypass_consent(driver)
          videos.add_route_record(route[0], RouteRecord.SUCCESS, route[1])
          return
        except Exception as e:
          videos.add_route_record(route[0], RouteRecord.TYPE_FAILURE)
          raise e
      else:
        raise Exception("Invalid route type: " + route[0])

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
      combined_log("html", (colors.FAIL, f"Your videos.json is empty!"))
      sys.exit()
    targeted_videos = [Video(id, info, False) for id, info in video_dict.items()]
    print(colors.OKGREEN[0] + f'{len(targeted_videos)} videos loaded' + colors.ENDC)
    if os.path.isfile('fake_watch_videos.json'):
      with open('fake_watch_videos.json', 'r', encoding='utf-8') as fp:
        all_videos = targeted_videos + [Video(id, info, True) for id, info in json.load(fp).items()]*jumping_video_boost
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
      print("Reloading videos...")
      try:
        self.targeted_videos, self.all_videos = self.load()
        self.hash = new_hash
      except:
        traceback.print_exc()
  def add_route_record(self, route_type, record_type, route_data=None):
    if not route_type in self.route_records:
      self.route_records[route_type] = RouteRecord(record_type, route_data)
    else:
      self.route_records[route_type].add_record(record_type, route_data)

def needed_browsers():
  return min(max_browsers, max(0, browser_ratio * (max_video_players - video_player_count.value) + video_player_count.value))


def get_null_path():
  if os.name == 'nt':
    return 'nul'
  elif os.name == 'posix':
    return '/dev/null'
  else:
    raise Exception("Operating system not supported: " + os.name)
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
  options.set_preference("webgl.disabled", "false")
  options.set_preference("privacy.firstparty.isolate", "true")
  options.set_preference("security.ssl.enable_false_start", "false")
  options.accept_insecure_certs = True
  if firefox_path:
    options.binary = firefox_path
  driver = selenium.webdriver.Firefox(options=options, service=service)
  driver_list.append(driver)
  driver.set_window_size(sizes[0], sizes[1])
  return driver

accept_texts = ("j'accepte", "i agree", "jag godkänner", "ich stimme zu", "acepto", "accepto", "accetto", "aceito", "ak stem in", "jeg accepterer", "nõustun", "souhlasím", "ik ga akkoord", "принимаю", "saya setuju", "hyväksyn", "ຂ້າພະເຈົ້າຍອມຮັບ", "我同意")
def bypass_consent(driver):
  try:
    consent = driver.find_element(By.XPATH, "//*[lower-case(.)={accept_texts}]")
    driver.execute_script("arguments[0].scrollIntoView();", consent)
    consent.click()
  except selenium.common.exceptions.NoSuchElementException:
    pass

def bypass_unsupported_browser(driver):
  time.sleep(random.uniform(1, 2))
  while 'www.youtube.com/supported_browsers' in driver.current_url:
    driver.find_element(By.CSS_SELECTOR, "a#return-to-youtube").click()
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
    combined_log(log_regular_events, (colors.OKBLUE, identifier + "No ads found"))
  else:
    try:
      combined_log(log_regular_events, (colors.OKBLUE, identifier + "Skipping Ads..."))
      skip_button = WebDriverWait(driver, 20).until(EC.element_to_be_clickable(
          (By.CLASS_NAME, "ytp-ad-skip-button")))
      time.sleep(random.uniform(0.1, 5))
      skip_button.click()
    except Exception as e:
      combined_log(log_regular_errors, (colors.OKBLUE, identifier + f"Ad skipping exception: {repr(e)}"))
  bypass_other_popups(driver)

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
      except selenium.common.exceptions.NoSuchElementException:
        continue
      WebDriverWait(driver, 30).until(EC.element_to_be_clickable(matcher))
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
  while not 'www.youtube.com/results' in driver.current_url:
    if random.randrange(2):
      search_bar.send_keys(Keys.ENTER)
    else:
      try:
        driver.find_element(By.XPATH, '//*[@id="search-icon-legacy"]').click()
      except Exception:
        driver.execute_script('document.querySelector("#search-icon-legacy").click()')
  finder = make_video_finder(lambda title: (By.XPATH, f'//*[@title="{title}"]'))
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
  finder = make_video_finder(lambda title: (By.XPATH, f'//*[@title="{title}"]'))
  for i in range(10):
    result = finder(driver)
    if result:
      return result
    time.sleep(random.uniform(0.5, 1.5))
    if not driver.find_elements(By.CSS_SELECTOR, 'ytd-continuation-item-renderer'):
      break
    WebDriverWait(driver, 30).until(EC.visibility_of_element_located(
      (By.TAG_NAME, 'body'))).send_keys(Keys.CONTROL, Keys.END)

def check_title(driver):
  for video in videos.targeted_videos:
    if video.title in driver.title: return True
    for alt in video.alt_titles:
      if alt in driver.title: return True

def play_video(driver):
  if not check_title(driver):
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
      try:
        driver.execute_script(
          "document.querySelector('button.ytp-play-button.ytp-button').click()")
      except Exception:
        pass

def play_music(driver, title):
  if not check_title(driver):
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
    play_music(driver, title)
    view_stat = 'Music'
  else:
    content_type = 'Video'
    play_video(driver)
    if bandwidth:
      save_bandwidth(driver)
    change_playback_speed(driver)
    view_stat = WebDriverWait(driver, 30).until(EC.visibility_of_element_located(
      (By.XPATH, '//span[@class="view-count style-scope ytd-video-view-count-renderer"]'))).text

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
        combined_log(log_regular_events, (colors.OKGREEN, identifier + "Stream found, "), (colors.OKCYAN, f"{view_stat} "))
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
      combined_log(log_regular_events, (colors.OKGREEN, identifier + f"{content_type} found, Watch Duration : {duration} "))
    except Exception:
      combined_log('html', (colors.FAIL, identifier + "Suppressed exception before playing: {traceback.format_exc()}"))

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

def save_bandwidth(driver):
  try:
    driver.find_element_by_css_selector(By.CSS_SELECTOR,
      "button.ytp-button.ytp-settings-button").click()
    driver.find_element(By.XPATH,
      "//div[contains(text(),'Quality')]").click()

    random_quality = random.choice(['144p', '240p', '360p'])
    quality = WebDriverWait(driver, 10).until(EC.element_to_be_clickable(
      (By.XPATH, f"//span[contains(string(),'{random_quality}')]")))
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
    driver.find_element(By.ID, 'movie_player').send_keys('<'*random.randrange(3) + 1)
  elif playback_speed == 3:
    driver.find_element(By.ID, 'movie_player').send_keys('>'*random.randrange(3) + 1)


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
      elif command == 'k':
        press = random.randrange(2)
        if press:
          movie_player.send_keys(command)
        for _ in range(2, 5):
          driver.execute_script(f'window.scrollBy(0, {random.uniform(300, 700)});')
          time.sleep(random.uniform(0.5, 3))
        driver.execute_script("arguments[0].scrollIntoView();", movie_player)
        if press:
          movie_player.send_keys(command)
      else:
        movie_player.send_keys(command*(random.randrange(5)+1))
  except Exception:
    combined_log('html', (colors.FAIL, identifier + f"Random command error: {traceback.format_exc()}"))

def quit_driver(driver):
  driver_list.remove(driver)
  driver.quit()

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
                combined_log('html', (colors.FAIL, identifier + f"Can't find a recommended video from {current.title}, opening a new one"))
                current = random.choice(videos.targeted_videos)
                current.open(identifier, driver)
              else:
                combined_log(log_regular_events, (colors.OKBLUE, identifier + f"Jumped '{current.title}' --> '{next.title}'"))
                current = next
              play(identifier, proxy.url, driver, current.title, current.fake_watch)
          finally:
            video_player_count.increment(-1)
        else:
          combined_log(log_reached_limit, (colors.OKBLUE, identifier + f"Reached video player limit"))
          time.sleep(over_limit_sleep)
          break
      combined_log(log_regular_events, (colors.OKBLUE, identifier + "Closing video player"))
    except (FirstPageError, FirstActionError, LoadingError) as e:
      cooldowns.add(proxy.url, SLOW_PROXY_COOLDOWN)
      combined_log(log_regular_errors, (colors.FAIL, identifier + f"{type(e).__name__}! Slow internet or stuck at recaptcha"))
      return
    except selenium.common.exceptions.WebDriverException:
      cooldowns.add(proxy.url, SLOW_PROXY_COOLDOWN)
      combined_log(log_regular_errors, (colors.FAIL, identifier + f"WebDriverException: {traceback.format_exc()}"))
      return
    except Exception:
      combined_log('html', (colors.FAIL, identifier + f"Watch loop exception : {traceback.format_exc()}"))
    finally:
      quit_driver(driver)
  except TerminatedError:
    print(f"{identifier}terminated")
  except Exception:
    combined_log('html', (colors.FAIL, identifier + f"Main viewer : {traceback.format_exc()}"))
  finally:
    browser_count.increment(-1)

def thread_wrapper(msg, func, *args):
  try:
    func(*args)
  except Exception:
    combined_log('html', (colors.FAIL, f"{msg} error: {traceback.format_exc()}"))
  if terminated:
    print(f"{msg} exited")

def check_monitored_files():
  while not terminated:
    time.sleep(FILE_CHECK_PERIOD)

def exit_report():
  print_route_records()
  print_view_records()

def print_view_records():
  print(f'Views: {views.value - og_views}')
  print(f'Hours: {watch_time.value - og_watch_time}')
def print_route_records():
  print('S: success, C: connection failure, F: other failure')
  if videos.route_records:
    for type, record in list(videos.route_records.items()):
      print(f'{type}: {record}')
  else:
    print('No Data')

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

def update_database():
  global stats_db, cooldowns
  stats_db = sqlite3.connect(STAT_DATABASE)
  cooldowns = Cooldowns()
  try:
    init_database()
    while True:
      time.sleep(15)
      try:
        stats_db.execute("UPDATE statistics SET hours = ? WHERE date = ?", (watch_time.value, today))
        stats_db.commit()
        cooldowns.commit()
        videos.detect_changes()
      except Exception:
        combined_log('html', (colors.FAIL, f"Database update error: {traceback.format_exc()}"))
      if terminated:
        break
  finally:
    stats_db.close()
    cooldowns.db.close()

def periodic_update():
  proxies.refresh()
  random.shuffle(videos.targeted_videos)
  random.shuffle(videos.all_videos)

def main():
  global terminated
  global add_thread

  def add_thread(msg, func, *args):
    thread = threading.Thread(target=thread_wrapper, args=(msg, func, *args))
    thread.start()
    return thread
  add_thread("Database udpate", update_database)
  webserver_thread = api and add_thread("Web server", website.start_server, host, port)
  for _ in range(proxy_thread_count):
    add_thread("Proxy checker", proxies.check_proxies)
  try:
    while True:
      try:
        process_cmd(input())
      except Exception:
        combined_log('html', (colors.FAIL, f"CLI error: {traceback.format_exc()}"))
  except KeyboardInterrupt:
    try:
      terminated = True
      exit_report()
      print()
      print("Stopping subprocesses... please wait")
      if webserver_thread and webserver_thread.is_alive():
        requests.post(f'http://127.0.0.1:{port}/shutdown')
      for driver in driver_list:
        driver.quit()
    except Exception:
      traceback.print_exc()
    finally:
      sys.exit()
  except Exception:
    traceback.print_exc()

if __name__ == '__main__':
  for _ in range(9):
    try:
      useragents = fake_useragent.UserAgent()
      break
    except Exception: pass
  else:
    useragents = fake_useragent.UserAgent()

  if not os.path.isfile('config.json'):
    create_config()
  with open('config.json', 'r') as openfile:
    config = json.load(openfile)

  jumping_video_boost = config.get("jumping_video_boost", 1)
  api = config["http_api"]["enabled"]
  host = config["http_api"]["host"]
  port = config["http_api"]["port"]
  database = config["database"]
  search_boost = config["search_boost"]
  headless = config["headless"]
  filter_anonymity = config["filter_anonymity"]
  firefox_path = config["firefox_path"]
  minimum = config["minimum_percent"] / 100
  maximum = config["maximum_percent"] / 100
  background = config["background"]
  bandwidth = config["bandwidth"]
  playback_speed = config["playback_speed"]
  proxy_thread_count = config["proxy_thread_count"]
  browser_ratio = config["browser_per_video_player"]
  max_video_players = config["video_player_count"]
  max_browsers = config.get("max_browsers", 20)
  over_limit_sleep = proxy_thread_count*OVER_LIMIT_SLEEP_UNIT

  videos = Videos()
  proxies = Proxies()

  main()
