import requests
import fake_useragent
import re
import traceback
import concurrent.futures
import random
import threading
import argparse
import os

re_ip = r"(\d+\.\d+\.\d+\.\d+)"
re_table = re.compile(re_ip + r"</t[hd]><t[hd]>(\d+)", re.DOTALL)
re_link_table = re.compile(re_ip + r"</a></td>\s*<td.*?>(\d+)")
re_json = re.compile(re_ip + r'", "PORT": "(\d+)', re.DOTALL)
urls = set()
result = []
naive_count = 0

def clear():
  global naive_count
  urls.clear()
  result.clear()
  naive_count = 0

def add_result(type, url):
  global naive_count
  naive_count += 1
  if not url in urls:
    urls.add(url)
    result.append((type, url))

def scrape():
  for _ in range(9):
    try:
      useragents = fake_useragent.UserAgent()
      break
    except Exception: pass
  else:
    useragents = fake_useragent.UserAgent()

  result_lock = threading.Lock()
  def request(url, method='GET', data=None, proxies=None):
    return requests.request(method, url, data=data, proxies=proxies, headers={"User-Agent": useragents.random})
  def simple_regex(raw, type, regex):
    for host, port in regex.findall(raw):
      yield f'{host}:{port}'
  def raw_proxies(raw, type):
    for line in raw.split('\r\n' if '\r\n' in raw else '\n'):
      if line:
        yield line

  # We will eat KeyboardInterrupt to let the user cancel scraping if they are good with the current number of proxies
  try:
    def get_proxy(func, type, url, *args):
      for try_idx in reversed(range(10)):
        try:
          page = request(url).text
          with result_lock:
            got_any = False
            for proxy in func(page, type, *args):
              got_any = True
              add_result(type, proxy)
            if not got_any:
              continue
            elif arguments.verbose:
              print(f'Naive: {naive_count}, actual: {len(result)}')
        except Exception as e:
          if not try_idx:
            traceback.print_exc()
        else:
          return page
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
      futures = []
      def add_source(func, *args):
        futures.append(executor.submit(get_proxy, func, *args))

      def paginated(type, url, regex, page_count_regex, increment, template):
        first = get_proxy(simple_regex, type, url, regex)
        page_count = int(page_count_regex.findall(first)[-1])
        for i in range(1, page_count):
          get_proxy(simple_regex, 'http', template.format(i*increment), regex)
      re_last_page = re.compile('data-ci-pagination-page="(\\d+)">Last')
      futures.append(executor.submit(paginated, 'http', "https://www.iplocation.net/proxy-list",
          re_link_table, re_last_page, 10, "https://www.iplocation.net/proxy-list/index/{0}"))
      re_last_page = re.compile('(\\d+)</a></li><li class=next_array>')
      futures.append(executor.submit(paginated, 'http', "https://hidemy.name/en/proxy-list/?type=hs",
          re_table, re_last_page, 64, "https://hidemy.name/en/proxy-list/?type=hs&start={0}#list"))
      futures.append(executor.submit(paginated, 'socks4', "https://hidemy.name/en/proxy-list/?type=4",
          re_table, re_last_page, 64, "https://hidemy.name/en/proxy-list/?type=4&start={0}#list"))
      futures.append(executor.submit(paginated, 'socks5', "https://hidemy.name/en/proxy-list/?type=5",
          re_table, re_last_page, 64, "https://hidemy.name/en/proxy-list/?type=5&start={0}#list"))

      add_source(simple_regex, 'http', "https://squidproxyserver.com/", re_table)
      add_source(simple_regex, 'http', "https://free-proxy-list.net/", re_table)
      add_source(simple_regex, 'socks4', "https://www.socks-proxy.net/", re_table)
      add_source(simple_regex, 'http', "https://www.us-proxy.org/", re_table)
      add_source(simple_regex, 'http', "https://free-proxy-list.net/uk-proxy.html", re_table)
      add_source(simple_regex, 'http', "https://www.sslproxies.org/", re_table)
      add_source(simple_regex, 'http', "https://free-proxy-list.net/anonymous-proxy.html", re_table)
      add_source(simple_regex, "socks4", "https://www.proxy-list.download/api/v2/get?l=en&t=socks4", re_json)
      add_source(simple_regex, "socks5", "https://www.proxy-list.download/api/v2/get?l=en&t=socks5", re_json)
      add_source(simple_regex, "http", "https://www.proxy-list.download/api/v2/get?l=en&t=http", re_json)
      add_source(simple_regex, "http", "https://www.proxy-list.download/api/v2/get?l=en&t=https", re_json)
      add_source(raw_proxies, "http", "https://api.proxyscrape.com/v2/?request=getproxies&protocol=http&timeout=10000&country=all&ssl=all&anonymity=all&simplified=true")
      add_source(raw_proxies, "socks4", "https://api.proxyscrape.com/v2/?request=getproxies&protocol=socks4&timeout=10000&country=all&ssl=all&anonymity=all&simplified=true")
      add_source(raw_proxies, "socks5", "https://api.proxyscrape.com/v2/?request=getproxies&protocol=socks5&timeout=10000&country=all&ssl=all&anonymity=all&simplified=true")
      add_source(raw_proxies, 'http', 'https://raw.githubusercontent.com/clarketm/proxy-list/master/proxy-list-raw.txt')
      add_source(raw_proxies, 'http', 'https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt')
      add_source(raw_proxies, 'socks4', 'https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/socks4.txt')
      add_source(raw_proxies, 'socks5', 'https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/socks5.txt')
      add_source(raw_proxies, 'http', 'https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/proxy.txt')
      add_source(raw_proxies, 'http', 'https://raw.githubusercontent.com/sunny9577/proxy-scraper/master/proxies.txt')

      for future in concurrent.futures.as_completed(futures):
        try:
          data = future.result()
        except Exception as exc:
          print(f'Got an exception: {exc}')
  except KeyboardInterrupt:
    pass
  return result

def load_proxies(path):
  with open(path, 'r') as fp:
    for num, line in enumerate(fp):
      try:
        type, address = line.split()
        add_result(type, address)
      except Exception as e:
        raise ValueError(f"Invalid line {num+1}: {line}") from e

if __name__ == '__main__':
  parser = argparse.ArgumentParser(description="scrape proxies and output them to a file")
  parser.add_argument("output", nargs='?', default='proxy_list.txt', help="export scraped proxy to FILE", metavar="FILE")
  parser.add_argument("-o", "--overwrite", dest='append', action='store_false', default=True, help="overwrite any existing file")
  parser.add_argument("-q", "--quiet", dest='verbose', action='store_false', default=True, help="be quiet")
  arguments = parser.parse_args()

  if arguments.append and os.path.isfile(arguments.output):
    load_proxies(arguments.output)
    if arguments.verbose:
      print(f"Loaded {len(result)} existing proxies")
  scrape()
  with open(arguments.output, 'w') as fp:
    for type, address in result:
      fp.write(f"{type} {address}\n")
