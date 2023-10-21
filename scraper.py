from requests_html import HTML
from typing import List
import cloudscraper
from progressbar import progressbar
import re
import os
import json


class Regex:
    @staticmethod
    def match(pattern, text):
        return re.search(pattern, text) is not None


class FileHandler:

    @staticmethod
    def readJSON(path : str):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    @staticmethod
    def readLines(path: str):
        with open(path, 'r', encoding='utf-8') as f:
            return [line.strip() for line in f.readlines()]
    
    @staticmethod
    def writeList(list, path: str):
        with open(path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(list))

    @staticmethod
    def writeMatrix(matrix, path: str, delimiter=';'):
        with open(path, 'w', encoding='utf-8') as f:
            f.write(f'{delimiter.join()}\n')
            for row in matrix:
                f.write(f'{delimiter.join(row)}\n')

    @staticmethod
    def saveScrapedPages(data: List[dict]):
        with open( 'data.json', 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False)


    @staticmethod
    def saveImage(bytes: bytes, path: str):
        with open(path, '+wb', encoding='utf-8') as f:
            f.write(bytes)


class RequestMaker:
    def __init__(self):
        self.__scraper = cloudscraper.create_scraper()

    def getDom(self, url, loadJS=False):
        response = self.__scraper.get(url)
        dom = HTML(html=response.content)
        if loadJS:
            dom.render()
        return dom

    def downloadImage(self, src):
        response = self.__scraper.get(src)
        bytes = response.content
        return bytes


class MonsterScaper:
    PAGE_ID = 0

    def __init__(self):
        self.__scraper = RequestMaker()

    def all_locales(self):
        BASE_URL = f'https://www.monsterenergy.com'
        dom = self.__scraper.getDom(BASE_URL)
        links: List[str] = dom.links
        REGEX_LOCALE = 'https://www.monsterenergy.com/\w{2}-\w{2}/$'
        locale_links = list(set([link for link in links if Regex.match(REGEX_LOCALE, link)]))
        locales = list(map(lambda l : l[-6:-1], locale_links))
        return locales

    def all_drinks_by_locale(self, locale):
        BASE_URL = f'https://www.monsterenergy.com'
        GATHER_URL = f'{BASE_URL}/{locale}/energy-drinks'
        dom = self.__scraper.getDom(GATHER_URL)
        links: List[str] = dom.links
        REGEX_DRINK = '.*/energy-drinks/.*?/.*?/$'
        drinks = list(set([link for link in links if Regex.match(REGEX_DRINK, link)]))
        drinks = [f'{BASE_URL}{drink}' for drink in drinks]
        return drinks

    def scrape_page(self, url, saveImage=False):
        dom = self.__scraper.getDom(url)
        name = self.__scrape_name(url)
        category = self.__scrape_category(url)
        locale = self.__scrape_locale(url)
        flavor = self.__scrape_flavor(dom)
        mainTitle = self.__scrape_main_title(dom)
        mainDescription = self.__scrape_main_description(dom)
        detailsTitle = self.__scrape_details_title(dom)
        detailsDescription = self.__scrape_details_description(dom)
        detailsNutrition = self.__scrape_details_nutrition(dom)
        detailsIngredients = self.__scrape_details_ingredients(dom)
        imageSource = self.__scrape_image(dom)
        imagePath = f'{IMAGES_PATH}/{locale}_{category.replace(" ","")}_{name.replace(" ","")}.png'

        if saveImage:
            imageBytes = self.__scraper.downloadImage(imageSource)
            FileHandler.saveImage(imageBytes, imagePath)

        MonsterScaper.PAGE_ID+=1

        return {
            'id': MonsterScaper.PAGE_ID,
            'name': name,
            'category': category,
            'locale': locale,
            'flavor': flavor,
            'main Title': mainTitle,
            'main Description': mainDescription,
            'details Title': detailsTitle,
            'details Description': detailsDescription,
            'details Nutrition': detailsNutrition,
            'details Ingredients': detailsIngredients,
            'image Source': imageSource,
            'image Path': imagePath
        }

    def __scrape_name(self, url: str) -> str:
        splitted = url.split('/')
        return splitted[-2].replace('-', ' ').title()

    def __scrape_category(self, url: str) -> str:
        splitted = url.split('/')
        return splitted[-3].replace('-', ' ').title()
    
    def __scrape_locale(self, url: str) -> str:
        splitted = url.split('/')
        return splitted[-5]

    def __scrape_flavor(self, dom: HTML) -> str:
        xpath = '//div[@class="prodInner"]//li[@class="list-inline-item flav"]//h2[2]'
        h2 = dom.xpath(xpath, first=True)
        return h2.text if h2 else ''

    def __scrape_main_title(self, dom: HTML) -> str:
        xpath = '//div[@class="prodInner"]//div[contains(@class,"headOne" )]'
        div = dom.xpath(xpath, first=True)
        return div.text if div else ''

    def __scrape_main_description(self, dom: HTML) -> str:
        xpath = '//div[@class="prodInner"]//div[@class="col-12 col-lg-8"]//p'
        p = dom.xpath(xpath, first=True)
        return p.text if p else ''

    def __scrape_details_title(self, dom: HTML) -> str:
        xpath = '//div[@id="nav-details"]/h3'
        h3 = dom.xpath(xpath, first=True)
        return h3.text if h3 else ''

    def __scrape_details_description(self, dom: HTML) -> str:
        xpath = '//div[@id="nav-details"]/p'
        p = dom.xpath(xpath, first=True)
        return p.text if p else ''

    def __scrape_details_nutrition(self, dom: HTML) -> List[List[str]]:
        xpath = '//div[@id="nav-nutrition"]/table'
        table = dom.xpath(xpath, first=True)
        splitted = table.full_text.splitlines()
        last_idx = 0
        better = []
        for idx in range(len(splitted)-1):
            curr = splitted[idx].strip()
            next = splitted[idx+1].strip()
            if curr != '' and last_idx+1 < idx:
                better.append([curr, next])
                last_idx = idx
        return better

    def __scrape_details_ingredients(self, dom: HTML) -> str:
        xpath = '//div[@id="nav-ingredients"]/p'
        p = dom.xpath(xpath, first=True)
        return p.text if p else ''

    def __scrape_image(self, dom: HTML) -> str:
        xpath = '//div[@class="prodInner"]//img[@class="can"]'
        img = dom.xpath(xpath, first=True)
        return img.attrs.get('src') if img else ''


IMAGES_PATH = './assets'
LOCALES_PATH = 'locales.txt'
LINKS_PATH = 'links.txt'
DATA_PATH = 'data.json'

scraper = MonsterScaper()

# SCRAPE LOCALES
# locales = scraper.all_locales()
# FileHandler.writeList(sorted(locales), LOCALES_PATH)
# OR READ THEM FROM OLD FILE
# locales = FileHandler.readLines(LOCALES_PATH)

# SCRAPE ALL DRINK LINKS FOR EVERY LOCALE
# all_links = set()
# for locale in progressbar(locales, redirect_stdout=True):
#     links = scraper.all_drinks_by_locale(locale)
#     all_links.update(links)
# FileHandler.writeList(sorted(all_links), LINKS_PATH)
# OR READ THEM FROM OLD FILE
# all_links = FileHandler.readLines(LINKS_PATH)

# SCRAPE ALL PAGES
# scraped_pages = []
# for link in progressbar(FileHandler.readLines(LINKS_PATH), redirect_stdout=True):
#     print(link)
#     page = scraper.scrape_page(link, saveImage=False)
#     scraped_pages.append(page)
# FileHandler.saveScrapedPages(scraped_pages)
# os.system(f'optimize-images -mw 200 -rc {IMAGES_PATH}')
# OR READ THEM FROM OLD FILE
# data = FileHandler.readJSON(DATA_PATH)
# print(data[0])