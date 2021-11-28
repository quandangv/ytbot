import urllib.request
import json

base_video_url = 'https://www.youtube.com/watch?v='

def update_channel_videos(api_key, channel_id, video_dict = {}):
  if not isinstance(video_dict, dict):
    video_dict = {}
  base_search_url = 'https://www.googleapis.com/youtube/v3/search?'
  first_url = base_search_url+'key={}&channelId={}&part=snippet,id&order=date&maxResults=25'.format(api_key, channel_id)
  url = first_url
  while True:
    inp = urllib.request.urlopen(url)
    resp = json.load(inp)
    for i in resp['items']:
      if i['id']['kind'] == "youtube#video":
        id = i['id']['videoId']
        if id in video_dict:
          video_dict[id]['title'] = i['snippet']['title']
        else:
          video_dict[id] = {
            'title': i['snippet']['title'],
            'urls': [base_video_url + id],
            'searches': []
          }
    try:
      next_page_token = resp['nextPageToken']
      url = first_url + '&pageToken={}'.format(next_page_token)
    except:
      break
  return video_dict

def update_video_info(api_key, video_id, video_attrs = None):
  if not isinstance(video_attrs, dict):
    video_attrs = None
  base_search_url = 'https://www.googleapis.com/youtube/v3/videos?'
  first_url = base_search_url+'key={}&id={}&part=snippet'.format(api_key, video_id)
  url = first_url
  inp = urllib.request.urlopen(url)
  resp = json.load(inp)
  for i in resp['items']:
    if video_attrs:
      video_attrs['title'] = i['snippet']['title']
    else:
      video_attrs = {
        'title': i['snippet']['title'],
        'urls': [base_video_url + video_id],
        'searches': []
      }
  return video_attrs

with open("config.json", 'r') as fp:
  config = json.load(fp)
api_key = config['api_key']
channel_id = config['channel_id']
with open("videos.json", 'r') as fp:
  videos = json.load(fp)
videos = update_channel_videos(api_key, channel_id, videos)
with open("videos.json", 'w') as fp:
  json.dump(videos, fp, indent=2)

with open("fake_watch_videos.json", 'r') as fp:
  fake_watch_videos = json.load(fp)
for video_id in fake_watch_videos:
  fake_watch_videos[video_id] = update_video_info(api_key, video_id, fake_watch_videos[video_id])
with open("fake_watch_videos.json", 'w') as fp:
  json.dump(fake_watch_videos, fp, indent=2)
