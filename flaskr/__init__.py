from flask import Flask, request, render_template, redirect, url_for
import os
import logging
from pymongo import MongoClient
import asyncio
from datetime import datetime
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from pymongo.server_api import ServerApi
from concurrent.futures import ProcessPoolExecutor
import json
from github import Github, GithubException

app = Flask(__name__)

mongo_host = os.getenv('MONGO_HOST', 'localhost')
mongo_port = os.getenv('MONGO_PORT', '27017')
mongo_user = os.getenv('MONGO_INITDB_ROOT_USERNAME', 'root')
mongo_pass = os.getenv('MONGO_INITDB_ROOT_PASSWORD', 'pass')
mongo_url = f"mongodb://{mongo_user}:{mongo_pass}@{mongo_host}:{mongo_port}/"


# Load the GitHub token and repository details from environment variables
github_token = os.getenv('GITHUB_TOKEN')
github_repo_name = os.getenv('GITHUB_REPO_NAME')
github_branch_name = os.getenv('GITHUB_BRANCH_NAME')


logging.info(f'GITHUB_REPO_NAME: {github_repo_name}')
logging.info(f'GITHUB_BRANCH_NAME: {github_branch_name}')


client = MongoClient(mongo_url, server_api=ServerApi('1'))
mydb = client["Projekt"]
scraped_urls_collection = mydb["scraped_urls"]


try:
    client.admin.command('ping')
    print("Pinged your deployment. You successfully connected to MongoDB!")
except Exception as e:
    print(e)


def serialize_document(doc):
    if '_id' in doc:
        doc['_id'] = str(doc['_id'])
    return doc


@app.route('/')
def home():
    return render_template('index.html')


@app.route('/export_to_github', methods=['POST'])
def export_to_github():
    logging.info('Attempting to connect to GitHub')
    g = Github(github_token)
    try:
        repo = g.get_repo(github_repo_name)
        logging.info(f'Connected to repo: {github_repo_name}')
    except GithubException as e:
        logging.error(f'Failed to connect to GitHub: {e}')
        return str(e), 500

    now = datetime.now()
    branch = github_branch_name

    # Collect all data from the MongoDB
    collections = [coll for coll in mydb.list_collection_names() if coll != "scraped_urls"]
    all_data = {}
    for collection_name in collections:
        collection = mydb[collection_name]
        documents = collection.find()
        all_data[collection_name] = [serialize_document(doc) for doc in documents]

    # Convert the data to JSON format
    all_data_json = json.dumps(all_data, indent=4)

    # Create a commit message
    commit_message = "Export scraped data"

    # Specify the file path in the repository
    file_path = f"data/scraped_data_{now.strftime('%H-%M-%d-%m-%Y')}.json"

    # Get the file if it exists in the repository
    try:
        contents = repo.get_contents(file_path, ref=branch)
        # Update the file
        repo.update_file(contents.path, commit_message, all_data_json, contents.sha, branch=branch)
    except:
        # If the file does not exist, create it
        repo.create_file(file_path, commit_message, all_data_json, branch=branch)

    return redirect(url_for('all_data'))

@app.route('/scrape', methods=['POST'])
async def scrape():
    url = request.form['url']
    already_scraped = scraped_urls_collection.find_one({"url": url})
    html = await fetch_content(url)

    phone_number_patterns = [
        r'\b(?:\d{3} \d{3} \d{3}|\d{2} \d{3} \d{2} \d{2})\b',  # xxx xxx xxx or xx xxx xx xx
        r'\b\d{3}-\d{3}-\d{3}\b',  # xxx-xxx-xxx
        r'\b\d{3}.\d{3}.\d{3}\b',  # xxx.xxx.xxx
        r'\b\d{4} \d{3} \d{3}\b',  # xxxx xxx xxx
        r'\b\+\d{2} \d{3} \d{3} \d{3}\b',  # +xx xxx xxx xxx
        r'\b\+\d{2} \d{3}-\d{3}-\d{3}\b'  # +xx xxx-xxx-xxx
    ]

    loop = asyncio.get_event_loop()
    with ProcessPoolExecutor() as executor:
        tasks = [
            loop.run_in_executor(executor, parse_phone_numbers, html, phone_number_patterns),
            loop.run_in_executor(executor, parse_emails, html),
            loop.run_in_executor(executor, parse_street_names, html),
            loop.run_in_executor(executor, parse_social_media, html, url)
        ]

        phone_numbers, emails, street_names, social_media = await asyncio.gather(*tasks)

    results = {
        "phone_numbers": phone_numbers if phone_numbers else [],
        "emails": emails if emails else [],
        "street_names": street_names if street_names else [],
        "social_media": social_media if social_media else []
    }

    if not already_scraped:
        site_collection = mydb[url.replace("https://", "").replace("/", "_")]
        if phone_numbers:
            site_collection.insert_one({"type": "phone_numbers", "data": phone_numbers})
        if emails:
            site_collection.insert_one({"type": "emails", "data": emails})
        if street_names:
            site_collection.insert_one({"type": "street_names", "data": street_names})
        if social_media:
            site_collection.insert_one({"type": "social_media", "data": social_media})

        scraped_urls_collection.insert_one({"url": url})

    return render_template('results.html', url=url, results=results)


@app.route('/all_data')
def all_data():
    collections = [coll for coll in mydb.list_collection_names() if coll != "scraped_urls"]
    all_data = {}
    for collection_name in collections:
        collection = mydb[collection_name]
        documents = collection.find()
        all_data[collection_name] = [serialize_document(doc) for doc in documents]

    return render_template('all_data.html', all_data=all_data, collections=collections, selected_data=None,
                           selected_collection=None, selected_data_type=None)


@app.route('/view_data', methods=['POST'])
def view_data():
    collection_name = request.form['collection']
    data_type = request.form['data_type']

    collection = mydb[collection_name]
    if data_type == 'none':
        selected_data = None
    else:
        documents = collection.find({"type": data_type})
        selected_data = [serialize_document(doc) for doc in documents]

    all_data = {collection_name: [serialize_document(doc) for doc in collection.find()]}
    collections = [coll for coll in mydb.list_collection_names() if coll != "scraped_urls"]

    return render_template('all_data.html', all_data=all_data, collections=collections,
                           selected_data=selected_data, selected_collection=collection_name,
                           selected_data_type=data_type)


@app.route('/delete_all', methods=['POST'])
def delete_all():
    collections = mydb.list_collection_names()
    for collection_name in collections:
        mydb[collection_name].drop()  # Drop collection
    return redirect(url_for('all_data'))










async def fetch_content(url):
    loop = asyncio.get_event_loop()
    response = await loop.run_in_executor(None, requests.get, url)
    if response.status_code == 200:
        return response.text
    else:
        return None


def parse_phone_numbers(html, patterns):
    if html:
        soup = BeautifulSoup(html, 'html.parser')
        phone_numbers = []
        for pattern in patterns:
            phone_numbers.extend(re.findall(pattern, soup.get_text()))
        return list(set(phone_numbers))
    else:
        return None


def parse_emails(html):
    if html:
        emails = re.findall(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', html)
        return list(set(emails))
    else:
        return None


def parse_street_names(html):
    if html:
        soup = BeautifulSoup(html, 'html.parser')
        street_names = [tag.get_text() for tag in soup.find_all(string=re.compile(r'^ul\.', re.IGNORECASE))]
        return list(set(street_names))
    else:
        return None


def parse_social_media(html, base_url):
    if html:
        social_media_patterns = {
            "twitter": r'https?://(?:www\.)?twitter\.com/[A-Za-z0-9_]+',
            "facebook": r'https?://(?:www\.)?facebook\.com/[A-Za-z0-9_.-]+',
            "instagram": r'https?://(?:www\.)?instagram\.com/[A-Za-z0-9_.-]+',
            "youtube": r'https?://(?:www\.)?youtube\.com/[A-Za-z0-9_./-]+'
        }
        soup = BeautifulSoup(html, 'html.parser')
        social_media_links = {platform: [] for platform in social_media_patterns}

        for a_tag in soup.find_all('a', href=True):
            href = a_tag['href']
            full_url = urljoin(base_url, href)

            for platform, pattern in social_media_patterns.items():
                if re.match(pattern, full_url):
                    social_media_links[platform].append(full_url)

        return {platform: list(set(links)) for platform, links in social_media_links.items() if links}
    else:
        return None


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000)
