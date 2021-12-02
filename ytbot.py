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
colors.FAIL[0]+r" ,---,  | |::|    |:::::|"+colors.OKBLUE[0]+"|   |:| |:: :   /::::::::\    ::::::|  \n" +
colors.FAIL[0]+r":___/:\;  |::|    |:'|::|"+colors.OKBLUE[0]+"|   |:|/:/  '  ;:::/  \:::;   |:'|::|  \n" +
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
      'https://www.bing.com/']
REFERERS = SEARCH_ENGINES + ['https://t.co/', '']

COMMANDS = [Keys.UP, Keys.DOWN, 'k', 'j', 'l', 't', 'c']

website.console = console
website.database = STAT_DATABASE

class PageLoadError(Exception):
  pass
class TerminatedError(Exception):
  pass
class QueryError(Exception):
  pass

today = str(datetime.datetime.today().date())
def init_database():
  global watch_time
  cursor = stats_db.cursor()
  cursor.execute("CREATE TABLE IF NOT EXISTS statistics (date TEXT, hours REAL)")
  try:
    cursor.execute("SELECT hours FROM statistics WHERE date = ?", (today,))
    watch_time = AtomicCounter(cursor.fetchone()[0])
  except Exception:
    cursor.execute("INSERT INTO statistics VALUES (?, ?)", (today, 0))
    watch_time = AtomicCounter(0)
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
    #options.page_load_strategy = 'eager'
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
    self.routes = []
    for type, arr in info['routes'].items():
      self.routes += [(type, data) for data in arr ]
  def open(self, identifier, driver):
    route = random.choice(self.routes)
    if route[0] == 'yt_search':
      spoof_referer(driver, random.choice(SEARCH_ENGINES), "https://www.youtube.com/")
      try:
        WebDriverWait(driver, 30).until(EC.visibility_of_element_located(
          (By.CSS_SELECTOR, 'input#search')))
      except selenium.common.exceptions.TimeoutException:
        raise PageLoadError()
      bypass_consent(identifier, driver)
      if not yt_search_video(driver, route[1], [self]):
        combined_log(log_regular_errors, (colors.FAIL, identifier + f"Search not found: {route[1]} :::: {self.title}. Fallback to url"))
        route = self.routes[0]
        if route[0] != 'url':
          raise Exception("Can't find a url for video")
      else:
        wait_for_video(driver)
        return
    if route[0] == 'url':
      spoof_referer(driver, random.choice(REFERERS), route[1])
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
    self.all_videos = self.targeted_videos + [Video(id, info, True) for id, info in fake_watch_dict.items()]*jumping_video_boost
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

def needed_browsers():
  return max(0, browser_ratio * (max_video_players - video_player_count.value) + video_player_count.value)


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
  options.set_preference("media.volume_scale", "0.01")
  options.set_preference("toolkit.cosmeticAnimations.enabled", "false")
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
  options.set_preference("webgl.disabled", "false")
  options.set_preference("privacy.firstparty.isolate", "true")
  options.set_preference("security.ssl.enable_false_start", "false")
  options.accept_insecure_certs = True
  options.page_load_strategy = 'eager'
  if firefox_path:
    options.binary = firefox_path
  driver = selenium.webdriver.Firefox(options=options, service=service)
  driver_list.append(driver)
  driver.set_window_size(sizes[0], sizes[1])
  return driver

def personalization(driver):
  search = driver.find_element(By.XPATH,
    f'//button[@aria-label="Turn {random.choice(["on","off"])} Search customization"]')
  driver.execute_script("arguments[0].scrollIntoView();", search)
  search.click()

  history = driver.find_element(By.XPATH,
    f'//button[@aria-label="Turn {random.choice(["on","off"])} YouTube History"]')
  driver.execute_script("arguments[0].scrollIntoView();", history)
  history.click()

  ad = driver.find_element(By.XPATH,
    f'//button[@aria-label="Turn {random.choice(["on","off"])} Ad personalization"]')
  driver.execute_script("arguments[0].scrollIntoView();", ad)
  ad.click()

  confirm = driver.find_element(By.XPATH, '//button[@jsname="j6LnYe"]')
  driver.execute_script("arguments[0].scrollIntoView();", confirm)
  confirm.click()


def bypass_consent(identifier, driver):
  try:
    consent = driver.find_element(By.XPATH, "//button[@jsname='higCR']")
  except selenium.common.exceptions.NoSuchElementException:
    try:
      consent = driver.find_element(By.XPATH, "//input[@type='submit' and @value='I agree']")
    except selenium.common.exceptions.NoSuchElementException:
      return
  combined_log(log_regular_events, (colors.OKBLUE, identifier + f"Bypassing consent..."))
  driver.execute_script("arguments[0].scrollIntoView();", consent)
  consent.click()
  if 'consent' in driver.current_url:
    personalization(driver)

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


def bypass_popup(driver):
  try:
    agree = WebDriverWait(driver, 5).until(EC.visibility_of_element_located(
      (By.XPATH, '//*[@aria-label="Agree to the use of cookies and other data for the purpos.namees described"]')))
    driver.execute_script(
      "arguments[0].scrollIntoView();", agree)
    time.sleep(1)
    agree.click()
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
      time.sleep(random.uniform(0.1, 5))
      skip_button.click()
    except Exception as e:
      combined_log(log_regular_errors, (colors.OKBLUE, identifier + f"Ad skipping exception: {repr(e)}"))
  bypass_other_popups(driver)

def type_keyword(driver, keyword, retry=False):
  input_keyword = driver.find_element_by_css_selector(By.CSS_SELECTOR, 'input#search')

  if retry:
    for _ in range(10):
      try:
        input_keyword.click()
        break
      except Exception:
        time.sleep(5)
        pass

  input_keyword.clear()
  for letter in keyword:
    input_keyword.send_keys(letter)
    time.sleep(random.uniform(.1, .4))

  if random.randrange(2):
    input_keyword.send_keys(Keys.ENTER)
  else:
    try:
      driver.find_element(By.XPATH, '//*[@id="search-icon-legacy"]').click()
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
        video_element = container.find_element(By.XPATH, f'//*[@title="{video.title}"]')
      except selenium.common.exceptions.NoSuchElementException:
        continue
      driver.execute_script("arguments[0].scrollIntoView();", video_element)
      time.sleep(1)
      bypass_popup(driver)
      try:
        video_element.click()
      except Exception:
        driver.execute_script("arguments[0].click();", video_element)
      return video
    time.sleep(2)
    WebDriverWait(driver, 30).until(EC.visibility_of_element_located(
      (By.TAG_NAME, 'body'))).send_keys(Keys.CONTROL, Keys.END)

def yt_search_video(driver, keyword, videos):
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
    try:
      driver.find_element(By.CLASS_NAME, 'ytp-ad-skip-button').click()
    except selenium.common.exceptions.NoSuchElementException:
      pass
    driver.find_element_by_css_selector(By.CSS_SELECTOR, '[title^="Pause (k)"]')
  except Exception:
    try:
      driver.find_element_by_css_selector(By.CSS_SELECTOR,
        'button.ytp-large-play-button.ytp-button').send_keys(Keys.ENTER)
    except Exception:
      try:
        driver.find_element_by_css_selector(By.CSS_SELECTOR, '[title^="Play (k)"]').click()
      except Exception:
        try:
          driver.execute_script(
            "document.querySelector('button.ytp-play-button.ytp-button').click()")
        except Exception:
          pass

def play_music(driver):
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

def play(identifier, cooldown_url, driver, fake_watch = False):
  skip_stuff(identifier, driver)
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
      play_video(driver)
      random_command(driver)
      if error == 5:
        break
      time.sleep(60)
      watch_time.increment(60/3600)
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

    update_interval = 5
    update_counter = 1
    prev_time = 0
    for _ in range(round(video_len/2)):
      if terminated:
        raise TerminatedError()
      time.sleep(random.uniform(10, 20))
      current_time = driver.execute_script(
        "return document.getElementById('movie_player').getCurrentTime()")
      if update_counter % update_interval:
        update_counter += 1
      elif database:
        watch_time.increment((current_time - prev_time)/3600)
        prev_time = current_time
      if content_type == 'Video':
        play_video(driver)
        random_command(driver)
      elif content_type == 'Music':
        play_music(driver)
      if current_time > video_len or driver.current_url != current_url:
        break
  if random.randrange(2):
    driver.find_element(By.ID, 'movie_player').send_keys('k')
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
    driver.execute_script(
      "arguments[0].scrollIntoView();", quality)
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


def random_command(driver):
  bypass_other_popups(driver)
  option = random.choices([1, 2], cum_weights=(0.7, 1.00), k=1)[0]
  if option == 2:
    command = random.choice(COMMANDS)
    if command in ['m', 't', 'c']:
      driver.find_element(By.ID, 'movie_player').send_keys(command)
    elif command == 'k':
      press = random.randrange(2)
      if press:
        driver.find_element(By.ID, 'movie_player').send_keys(command)
      for _ in range(2, 5):
        driver.execute_script(f'document.querySelector("#comments").scrollBy({random.uniform(300, 700)});')
        time.sleep(random.uniform(0.5, 3))
      driver.execute_script(
        'document.querySelector("#movie_player").scrollIntoView(true);')
      if press:
        driver.find_element(By.ID, 'movie_player').send_keys(command)
    else:
      driver.find_element(By.ID, 'movie_player').send_keys(command*(random.randrange(5)+1))

def quit_driver(driver):
  driver_list.remove(driver)
  driver.quit()

def view_thread(identifier, proxy):
  browser_count.increment()
  try:
    combined_log(log_proxy_events, (colors.OKGREEN, identifier + "Opening a driver..."))
    driver = get_driver(useragents.random, proxy)
    try:
      time.sleep(2)
      for _ in range(4):
        current = random.choice(videos.all_videos)
        current.open(identifier, driver)
        if video_player_count.value < max_video_players:
          try:
            video_player_count.increment()
            play(identifier, proxy.url, driver, current.fake_watch)
            for idx in range(random.randint(3, 5)):
              next = find_video(driver, videos.targeted_videos)
              if not next:
                combined_log('html', (colors.FAIL, identifier + f"Can't find a recommended video from {current.title}, opening a new one"))
                current = random.choice(videos.targeted_videos)
                current.open(identifier, driver)
              else:
                combined_log(log_regular_events, (colors.OKBLUE, identifier + f"Jumped '{current.title}' --> '{next.title}'"))
                current = next
              play(identifier, proxy.url, driver, current.fake_watch)
          finally:
            video_player_count.increment(-1)
        else:
          combined_log(log_reached_limit, (colors.OKBLUE, identifier + f"Reached video player limit"))
          time.sleep(over_limit_sleep)
          break
      combined_log(log_regular_events, (colors.OKBLUE, identifier + "Closing video player"))
    except PageLoadError:
      cooldowns.add(proxy.url, SLOW_PROXY_COOLDOWN)
      combined_log(log_regular_errors, (colors.FAIL, identifier + f"Page load error! Slow internet speed or stuck at recaptcha"))
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

def process_cmd(cmd):
  cmd = cmd.lower()
  global max_video_players
  global detailed_proxy_errors
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
  elif cmd[1:] in ['proxy errors', 'proxy_errors', 'pe']:
    detailed_proxy_errors = cmd[0] == '+'
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

  global max_browsers
  api = config["http_api"]["enabled"]
  jumping_video_boost = config.get("jumping_video_boost", 1)
  host = config["http_api"]["host"]
  port = config["http_api"]["port"]
  database = config["database"]
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
  over_limit_sleep = proxy_thread_count*OVER_LIMIT_SLEEP_UNIT

  videos = Videos()
  proxies = Proxies()

  main()
