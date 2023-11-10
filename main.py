import configparser
import datetime
import os
import re

import feedparser
from bs4 import BeautifulSoup
from jinja2 import Template
from openai import OpenAI

GPT_MODEL_3_5 = "gpt-3.5-turbo-16k-0613"
GPT_MODEL_4 = "gpt-4-0613"


# from dateutil.parser import parse

# Generate a fallback title for an entry if the regular title is not available
def generate_untitled(entry):
    """
    Generate a fallback title for the RSS entry.
    Tries to use the title, then the first 50 characters of the article,
    and finally the link as the last resort.

    Args:
        entry: The entry object from the RSS feed.

    Returns:
        A string representing the title of the entry.
    """
    try:
        return entry.title
    except AttributeError:
        try:
            return entry.article[:50]  # First 50 characters of the article
        except AttributeError:
            return entry.link  # URL if nothing else is available


# Configuration helpers to get and set configurations
def get_cfg(sec, name, default=None):
    """
    Get a configuration value for a given section and name.
    Falls back to a default value if not found.

    Args:
        sec: The section in the configuration file.
        name: The name of the configuration option.
        default: The default value to return if the option is not found.

    Returns:
        The configuration value as a string, or the default value.
    """
    value = config.get(sec, name, fallback=default)
    if value:
        return value.strip('"')


def set_cfg(sec, name, value):
    """
    Set a configuration value for a given section and name.

    Args:
        sec: The section in the configuration file.
        name: The name of the configuration option.
        value: The value to set for the option.
    """
    config.set(sec, name, '"%s"' % value)


# Cleans the HTML content from the unnecessary tags
def clean_html(html_content):
    """
    Clean the HTML content from unnecessary tags.

    Args:
        html_content: The HTML content as a string.

    Returns:
        The cleaned text suitable for summarization.
    """
    # Parse the HTML content with BeautifulSoup
    soup = BeautifulSoup(html_content, "html.parser")

    # Define tags to remove
    tags_to_remove = ['script', 'style', 'img', 'a', 'video', 'audio', 'iframe', 'input']

    # Remove the tags from the soup object
    for tag in tags_to_remove:
        for element in soup.find_all(tag):
            element.decompose()

    # Return the text part of the soup object
    return soup.get_text()


def filter_entry(entry, filter_apply, filter_type, filter_rule):
    """
    This function is used to filter the RSS feed.

    Args:
        entry: RSS feed entry
        filter_apply: title, article or link
        filter_type: include or exclude or regex match or regex not match
        filter_rule: regex rule or keyword rule, depends on the filter_type

    Raises:
        Exception: filter_apply not supported
        Exception: filter_type not supported
    """
    if filter_apply == 'title':
        text = entry.title
    elif filter_apply == 'article':
        text = entry.article
    elif filter_apply == 'link':
        text = entry.link
    elif not filter_apply:
        return True
    else:
        raise Exception('filter_apply not supported')

    if filter_type == 'include':
        return re.search(filter_rule, text)
    elif filter_type == 'exclude':
        return not re.search(filter_rule, text)
    elif filter_type == 'regex match':
        return re.search(filter_rule, text)
    elif filter_type == 'regex not match':
        return not re.search(filter_rule, text)
    elif not filter_type:
        return True
    else:
        raise Exception('filter_type not supported')


def read_entry_from_file(sec):
    """
    This function is used to read the RSS feed entries from the feed.xml file.

    Args:
        sec: section name in config.ini
    """
    out_dir = os.path.join(BASE, get_cfg(sec, 'name'))
    try:
        with open(out_dir + '.xml', 'r') as f:
            rss = f.read()
        feed = feedparser.parse(rss)
        return feed.entries
    except:
        return []


def truncate_entries(entries, max_entries):
    if len(entries) > max_entries:
        entries = entries[:max_entries]
    return entries


def gpt_summary(query, model, language):
    if language == "zh":
        messages = [
            {"role": "user", "content": query},
            {"role": "assistant",
             "content": f"请用中文总结这篇文章，首先提取出{keyword_length}个关键词，并将它们列成一个列表。然后，在{summary_length}字内写一个包含所有要点的总结。请将关键词和总结分开，并使用以下格式：'关键词：[关键词1], [关键词2], [关键词3], ...<br><br>总结：<br>[总结内容]'。"
             }
        ]
    else:
        messages = [
            {"role": "user", "content": query},
            {"role": "assistant",
             "content": f"Please summarize this article in {language}, starting with extracting {keyword_length} keywords and listing them. Then, write a summary that contains all the main points in {summary_length} words. Format your output by first presenting the keywords, followed by a line break, and then the summary. Use the following format: 'Keywords: [keyword1], [keyword2], [keyword3], ...<br><br>Summary:<br>[Summary content]'."
             }
        ]
    client = OpenAI(
        api_key=OPENAI_API_KEY,
        base_url="https://openkey.cloud/v1"
    )
    completion = client.chat.completions.create(
        model=model,
        messages=messages,
    )
    return completion.choices[0].message.content


def output(sec, language):
    """ output
    This function is used to output the summary of the RSS feed.

    Args:
        sec: section name in config.ini

    Raises:
        Exception: filter_apply, type, rule must be set together in config.ini
    """
    log_file = os.path.join(BASE, get_cfg(sec, 'name') + '.log')
    out_dir = os.path.join(BASE, get_cfg(sec, 'name'))
    # read rss_url as a list separated by comma
    rss_urls = get_cfg(sec, 'url')
    rss_urls = rss_urls.split(',')

    # RSS feed filter apply, filter title, article or link, summarize title, article or link
    filter_apply = get_cfg(sec, 'filter_apply')

    # RSS feed filter type, include or exclude or regex match or regex not match
    filter_type = get_cfg(sec, 'filter_type')

    # Regex rule or keyword rule, depends on the filter_type
    filter_rule = get_cfg(sec, 'filter_rule')

    # filter_apply, type, rule must be set together
    if filter_apply and filter_type and filter_rule:
        pass
    elif not filter_apply and not filter_type and not filter_rule:
        pass
    else:
        raise Exception('filter_apply, type, rule must be set together')

    # Max number of items to summarize
    max_items = get_cfg(sec, 'max_items')
    if not max_items:
        max_items = 0
    else:
        max_items = int(max_items)
    cnt = 0
    existing_entries = read_entry_from_file(sec)
    with open(log_file, 'a') as f:
        f.write('------------------------------------------------------\n')
        f.write(f'Started: {datetime.datetime.now()}\n')
        f.write(f'Existing_entries: {len(existing_entries)}\n')
    existing_entries = truncate_entries(existing_entries, max_entries=max_entries)
    # Be careful when the deleted ones are still in the feed, in that case, you will mess up the order of the entries.
    # Truncating old entries is for limiting the file size, 1000 is a safe number to avoid messing up the order.
    append_entries = []

    for rss_url in rss_urls:
        with open(log_file, 'a') as f:
            f.write(f"Fetching from {rss_url}\n")
            print(f"Fetching from {rss_url}")
        feed = feedparser.parse(rss_url)
        if feed.status != 200:
            with open(log_file, 'a') as f:
                f.write(f"Feed error: {feed.status}\n")
            continue
        if feed.bozo:
            with open(log_file, 'a') as f:
                f.write(f"Feed error: {feed.bozo_exception}\n")
            continue
        for entry in feed.entries:

            if cnt > max_entries:
                with open(log_file, 'a') as f:
                    f.write(f"Skip from: [{entry.title}]({entry.link})\n")
                break

            if entry.link.find('#replay') and entry.link.find('v2ex'):
                entry.link = entry.link.split('#')[0]

            if entry.link in [x.link for x in existing_entries]:
                continue

            if entry.link in [x.link for x in append_entries]:
                continue

            entry.title = generate_untitled(entry)

            try:
                entry.article = entry.content[0].value
            except:
                try:
                    entry.article = entry.description
                except:
                    entry.article = entry.title

            cleaned_article = clean_html(entry.article)

            if not filter_entry(entry, filter_apply, filter_type, filter_rule):
                with open(log_file, 'a') as f:
                    f.write(f"Filter: [{entry.title}]({entry.link})\n")
                continue

            #            # format to Thu, 27 Jul 2023 13:13:42 +0000
            #            if 'updated' in entry:
            #                entry.updated = parse(entry.updated).strftime('%a, %d %b %Y %H:%M:%S %z')
            #            if 'published' in entry:
            #                entry.published = parse(entry.published).strftime('%a, %d %b %Y %H:%M:%S %z')
            cleaned_article = clean_html(entry.article)

            if cnt > max_items:
                entry.summary = None
            elif OPENAI_API_KEY:
                token_length = len(cleaned_article)

                try:
                    cnt += 1
                    entry.summary = gpt_summary(cleaned_article, model=GPT_MODEL_3_5, language=language)
                    cnt += 1  # 只有成功生成摘要后才增加计数
                    with open(log_file, 'a') as f:
                        f.write(f"Token length: {token_length}\n")
                        f.write(f"Summarized using {GPT_MODEL_3_5}\n")
                except:
                    try:
                        entry.summary = gpt_summary(cleaned_article, model=GPT_MODEL_4, language=language)
                        cnt += 1  # 只有成功生成摘要后才增加计数
                        with open(log_file, 'a') as f:
                            f.write(f"Token length: {token_length}\n")
                            f.write(f"Summarized using {GPT_MODEL_4}\n")
                    except Exception as e:
                        entry.summary = None
                        with open(log_file, 'a') as f:
                            f.write(f"Summarization failed, append the original article\n")
                            f.write(f"error: {e}\n")

            append_entries.append(entry)
            with open(log_file, 'a') as f:
                f.write(f"Append: [{entry.title}]({entry.link}) Summary: {entry.summary}\n")

    with open(log_file, 'a') as f:
        f.write(f'append_entries: {len(append_entries)}\n')

    template = Template(open('template.xml').read())

    try:
        rss = template.render(feed=feed, append_entries=append_entries, existing_entries=existing_entries)
        with open(out_dir + '.xml', 'w') as f:
            f.write(rss)
        with open(log_file, 'a') as f:
            f.write(f'Finish: {datetime.datetime.now()}\n')
    except:
        with open(log_file, 'a') as f:
            f.write(f"error when rendering xml, skip {out_dir}\n")
            print(f"error when rendering xml, skip {out_dir}\n")


config = configparser.ConfigParser()
config.read('config.ini')
secs = config.sections()
# Maxnumber of entries to in a feed.xml file
max_entries = 1000

OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')
U_NAME = os.environ.get('U_NAME')
# deployment_url = f'https://{U_NAME}.github.io/RSS-GPT/'
deployment_url = f'https://github.com/ArnoFrost/RSS-GPT'
BASE = get_cfg('cfg', 'BASE')
keyword_length = int(get_cfg('cfg', 'keyword_length'))
summary_length = int(get_cfg('cfg', 'summary_length'))
language = get_cfg('cfg', 'language')

try:
    os.mkdir(BASE)
except:
    pass

feeds = []
links = []

for x in secs[1:]:
    output(x, language=language)
    feed = {"url": get_cfg(x, 'url').replace(',', '<br>'), "name": get_cfg(x, 'name')}
    feeds.append(feed)  # for rendering index.html
    links.append("- " + get_cfg(x, 'url').replace(',', ', ') + " -> " + deployment_url + feed['name'] + ".xml\n")


def append_readme(readme, links):
    with open(readme, 'r') as f:
        readme_lines = f.readlines()
    while readme_lines[-1].startswith('- ') or readme_lines[-1] == '\n':
        readme_lines = readme_lines[:-1]  # remove 1 line from the end for each feed
    readme_lines.append('\n')
    readme_lines.extend(links)
    with open(readme, 'w') as f:
        f.writelines(readme_lines)


append_readme("README.md", links)
append_readme("README-zh.md", links)

# Rendering index.html used in my GitHub page, delete this if you don't need it.
# Modify template.html to change the style
with open(os.path.join(BASE, 'index.html'), 'w') as f:
    template = Template(open('template.html').read())
    html = template.render(update_time=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), feeds=feeds)
    f.write(html)
