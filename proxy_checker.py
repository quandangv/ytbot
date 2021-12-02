import requests
import random
import re

timeout = (10, 20)
logging = False

_contact_msg = "contact my maintainers if this keep happening"
_ip_regex = re.compile(r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}')
_remote_regex = re.compile(r'REMOTE_ADDR = (\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})')

### THESE LINKS MAY GO DOWN AND NEED TO BE MAINTAINED ###
_ip_finders = [
  'https://api.ipify.org/',
  'https://api.my-ip.io/ip']
_proxy_judges = [
  'http://azenv.net/',
  'http://www.eliteproxyswitcher.com/proxyjudge.html',
  'http://proxyjudge.us/azenv.php']
_country_finder = 'https://ip2c.org/'

class Result:
  def __init__(self, protocols, anonymity, elapsed, remote_address):
    self.protocols = protocols
    self.anonymity = anonymity
    self.elapsed = elapsed
    self.remote_address = remote_address

class Checker:
  def __init__(self):
    self.ip = self.get_ip()
    self.judges = [url for url in _proxy_judges if requests.get(url).ok]
    if not self.judges:
      raise ConnectionError("All the proxy judges are down! Try reinitializing or " + _contact_msg)

  def get_ip(self):
    for finder in _ip_finders:
      r = requests.get(finder)
      if r.ok:
        return r.text
      if logging:
        print(f"Can't get my IP address through {finder}, {_contact_msg}")
    raise ConnectionError("Can't find my IP address, " + _contact_msg)

  def check_anonymity(self, judge_response):
    if self.ip in judge_response:
      return 'Transparent'
    for header in [
      'VIA',
      'X-FORWARDED-FOR',
      'X-FORWARDED',
      'FORWARDED-FOR',
      'FORWARDED-FOR-IP',
      'FORWARDED',
      'CLIENT-IP',
      'PROXY-CONNECTION']:
      if header in judge_response:
        return 'Anonymous'
    return 'Elite'

  def get_country(self, ip):
    response = requests.get(_country_finder + ip)
    if response and response.text[0] == '1':
      response = response.text.split(';')
      return [response[3], response[1]]
    return ['-', '-']

  def check_proxy(self, proxy, checked_type=['http', 'socks4', 'socks5'], check_country=True):
    responses = []
    protocols = set()
    elapsed = 0

    for protocol in checked_type:
      proxy_url = protocol + '://' + proxy
      try:
        response = requests.get(
            random.choice(self.judges),
            timeout=timeout,
            verify=False,
            proxies={'http': proxy_url, 'https': proxy_url})
        if response.ok:
          responses.append(response.text)
          protocols.add(protocol)
          elapsed += response.elapsed.total_seconds()
        elif logging:
          print(f'Got status code {response.status_code}')
      except Exception as e:
        if logging:
          print(e)
        pass

    if not responses:
      return None

    text = random.choice(responses)
    anonymity = self.check_anonymity(text)
    elapsed = elapsed / len(responses)

    remote_address = _remote_regex.search(text)
    remote_address = remote_address and remote_address.group(1)

    result = Result(protocols, anonymity, elapsed, remote_address)

    if check_country:
      country = self.get_country(_ip_regex.findall(proxy)[0])
      result.country = country[0]
      result.country_code = country[1]

    return result
