import argparse
import traceback
import os
import time

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as ec
from selenium.common.exceptions import TimeoutException

from urllib3.exceptions import MaxRetryError, ProtocolError

from urllib import parse
from bs4 import BeautifulSoup
import re

import pandas as pd
import json

from yt_scraper.logger import Logger
from yt_scraper.helpers import file_name_timer
from yt_scraper.inputs import input_data_name, states_input_name


EXTRACTION_FAILURE_MSG = "EXTRACTION_FAILED"

WEB_DRIVER = webdriver.Edge

WORDS_IN_NUMBERS = ['views', 'view',
                    'subscribers', 'subscriber',
                    'videos', 'video']

indian_units = {'lakh': 100_000, 'crore': 10_000_000}

def find_meta_description(chid, _in: WEB_DRIVER, _id, logger, xpath='*'):
    # Search for element in _in
    if _id == 'channel-handle':
        element_list = [element
                   for element in _in.find_elements(By.ID, _id)
                   if element.is_displayed()]
        if element_list:
            element = element_list[0]
        else :
            logger.log("Channel {} :: channel handle not found : ''"
                    "".format(chid),
                    'WARNING')
            return ""
    elif _id == 'channel-name':
        element = _in.find_element(By.CSS_SELECTOR, '#text.style-scope.ytd-channel-name')
    else: element = _in.find_element(By.XPATH, '//{}[@id="{}"]'.format(xpath, _id))
    # clean element name
    el_name = _id.replace('container', '').replace('-', ' ').strip()
    # If it's diplayed, get value.
    if element.is_displayed():
        value = element.text
        limit = min(40, len(value))
        logger.log("Channel {} :: {} found : {}"
                   "".format(chid, el_name, value[:limit].replace('\n', '\\n')))
        return value
    # Otherwise use an empty string.
    logger.log("Channel {} :: {} not found : ''"
               "".format(chid,el_name),
               'WARNING')
    return ""


def find_links(chid, _in:WEB_DRIVER, _id, logger, xpath='div'):
    # Search for element in _in
    element = _in.find_element(By.XPATH, '//{}[@id="{}"]'.format(xpath, _id))
    # clean element name
    el_name = _id.replace('container', '').replace('-', ' ').strip()
    # If it's diplayed, get value.
    if element.is_displayed():
        _html = element.get_attribute('innerHTML')
        _soup = BeautifulSoup(_html, 'html.parser')
        _values = _soup.find_all('a', class_='yt-simple-endpoint')
        values = [value['href'] for value in _values]
        logger.log("Channel {} :: {} found : {}"
                   "".format(chid, el_name, values))
        return values
    # Otherwise use an empty list.
    logger.log("Channel {} :: No link found."
                        "".format(chid), 'WARNING')
    return []

def find_stats(chid, _in: WEB_DRIVER , _id, logger, xpath='div'):
    # Search for element in _in
    elements = (_in.find_element(By.XPATH,
                                 '//{}[@id="{}"]'.format(xpath, _id))
                    .find_elements(By.TAG_NAME, 'yt-formatted-string'))
    # Extract the joined date
    joined_on = elements[1].find_elements(By.TAG_NAME, 'span')[-1]
    if joined_on.is_displayed():
        joined_on = joined_on.text
        logger.log("Channel {} :: joined date found : {}"
                   "".format(chid, joined_on))
    else:
        logger.log("Channel {} :: joined date not found."
                   "".format(chid), 'WARNING')
        joined_on = ""
    # Extract the total views
    ttl_views = elements[2]
    if ttl_views.is_displayed():
        ttl_views = ttl_views.text
        logger.log("Channel {} :: total views found : {}"
                   "".format(chid, ttl_views))
    else:
        logger.log("Channel {} :: total views not found."
                   "".format(chid), 'WARNING')
        ttl_views = ""
    # Return the joined date and the total views as a tuple
    return joined_on, ttl_views


class NoResultsException(Exception):
     
     def __init__(self, *args: object) -> None:
         self.message = "No Results Found"
         super().__init__(*args)



class Scrapper():

    def __init__(self,
                 to_scrape_channels: dict[str, dict],
                 cities_by_states: dict[str, list[str]],
                 logger=None) -> None:
        # Logging configuration.
        self.logger = logger or Logger()
        self.logger.log("Initiate the scrapper object.", _br=True)
        # Scrapper configuartion
        self.driver = WEB_DRIVER()
        self.long_wait = WebDriverWait(self.driver, 10)
        self.short_wait = WebDriverWait(self.driver, 2)
        self.items_separator = '\n'
        # Scarpper initial data
        self._f_to_scrape_channels = to_scrape_channels
        self._f_cities_by_states = cities_by_states
        # ...
        self.unscrapped_channels = {}
        self.scrapped_channels = {}
        self.ignored_channels = {}

    def extract_phone_numbers(self, about_description):
        phone_number_pattern = r'[1-9][0-9]{9}|\b\d{5}\s\d{5}\b'
        phone_numbers = re.findall(phone_number_pattern, about_description)
        return list({phone.replace(' ', '') for phone in phone_numbers})
            
    
    def clean_text_from_number(self, text_number, _for='subscribers'):
        """
        Clean a number provided in text with unit.
        """
        # If text number is empty, return it
        if not text_number:
            return ''
        # Vectorize the text number.
        text_vector: list = text_number.lower().split()[:-1]
        # Initiate the unit with 1
        unit = 1
        # Remove Lakh and Crore
        for u_label, u in indian_units.items():
            if u_label in text_vector:
                text_vector.remove(u_label)
                unit = u
        # Concatenate the remaning elements and remove commas
        text_number = ' '.join(text_vector).replace(',', '').strip()
        # Remove K suffix and set unit to one thousand
        if text_number.endswith('k'):
            text_number = text_number.removesuffix('k')
            unit = 1_000
        # Remove M suffix and set unit to one million
        elif text_number.endswith('m'):
            text_number = text_number.removesuffix('m')
            unit = 1_000_000
        # Try to convert the text number to a numeric number.
        try:
            return int(float(text_number)*unit)
        except:
            if text_number == 'no':
                return 0
            raise ValueError("{} count could not converted "
                             "to integer.".format(_for))

    def extract_city_and_state(self, about_description: str):
        about_description = about_description.lower()
        found_states = set()
        found_cities = set()
        for state, cities in self._f_cities_by_states.items():
            state_pattern = '\\b{}[.,;:!?]*\\b'.format(state)
            _states = re.findall(state_pattern, about_description)
            for city in cities:
                city_pattern = '\\b{}[.,;:!?]*\\b'.format(city)
                _cities = re.findall(city_pattern, about_description)
                if _cities:
                    found_cities.update(_cities)
            if _states:
                found_states.update(_states)
        return {'city': self.items_separator.join(found_cities),
                'state': self.items_separator.join(found_states)}

    def extract_links(self, links_list):
        telegram_links = []
        instagram_links = []
        other_links = []
        for link in links_list:
            try:
                parsed_link = parse.parse_qs(parse.urlparse(link)
                                                  .query)['q'][0]
            except KeyError:
                parsed_link = link
            if 't.me' in parsed_link:
                telegram_links.append(parsed_link)
                continue
            if 'instagram.com' in parsed_link:
                instagram_links.append(parsed_link)
                continue
            # NOTE: any other social media link, can be detected and then added
            # to the data in the same way.
            # E.g. Facebook
            ###################################################################
            # if 'facebook.com' in parsed_link:
            #     facebook_links.append(parsed_link)
            #     continue
            ###################################################################
            other_links.append(parsed_link)
        # Combine all the links into a ditionary.
        found_links = {'telegram_links': telegram_links,
                       'instagram_links': instagram_links,
                       'other_links': other_links}
        return found_links

    def save_unscrapped_channels(self, output_dir):
        # output files.
        output_filename = f"{output_dir}\\unscrapped_channels.json"
        # Save the uncleaned data to a json file.
        with open(output_filename, 'w+', encoding='utf-8') as output_file:
            json.dump(self.unscrapped_channels,
                      output_file,
                      indent=3,
                      ensure_ascii=False)
        # Inform success of saving
        self.logger.log("Unscrapped channels ({}) saved to {}"
                        "".format(len(self.unscrapped_channels),
                                  output_filename),
                        'INFO')
        
    def save_ignored_channels(self, output_dir):
        # output files.
        output_filename = f"{output_dir}\\ignored_channels.json"

        # Read previously ignored_channels
        try:
            with open(output_filename, 'r+', encoding='utf-8') as output_file:
                prev_ignored_channels = json.load(output_file)

            prev_ignored_channels.update(self.ignored_channels)
        except FileNotFoundError as e:
            prev_ignored_channels = self.ignored_channels

        # Save the uncleaned data to a json file.
        with open(output_filename, 'w+', encoding='utf-8') as output_file:
            json.dump(prev_ignored_channels,
                      output_file,
                      indent=3,
                      ensure_ascii=False)
        # Inform success of saving
        self.logger.log("Channels with no results ({}) saved to {}"
                        "".format(len(self.ignored_channels),
                                  output_filename),
                        'INFO')

    def save_scrapped_channels(self, output_dir):
        # output files.
        uncleaned_output_file = f"{output_dir}\\uncleaned_scrapped_channels.json"
        cleaned_output_file = f"{output_dir}\\cleaned_scrapped_channels.json"

        # Read previously scrapped_channels (uncleaned)
        try:
            with open(uncleaned_output_file, 'r+', encoding='utf-8') as output_file:
                prev_scrapped_channels = json.load(output_file)

            prev_scrapped_channels.update(self.scrapped_channels)
        except FileNotFoundError as e:
            prev_scrapped_channels = self.scrapped_channels

        # Save the uncleaned data to a json file.
        with open(uncleaned_output_file, 'w+', encoding='utf-8') as output_file:
            json.dump(prev_scrapped_channels,
                      output_file,
                      indent=3,
                      ensure_ascii=False)

        # Inform success of saving
        self.logger.log("Uncleaned scrapped channels saved to {}"
                        "".format(uncleaned_output_file), 'INFO')

        # Clean the data
        for chid, channel_data in self.scrapped_channels.items():

            descr = channel_data.get('description')
            subs = channel_data.get('subscriber_count')
            links = channel_data.get('other_links')
            videos = channel_data.get('videos_count')
            views = channel_data.get('total_views')
            phone_numbers = self.extract_phone_numbers(descr)
            found_links = self.extract_links(links)
            geography = self.extract_city_and_state(descr)
            subs = self.clean_text_from_number(subs)
            videos_count = self.clean_text_from_number(videos, 'videos')
            total_views = self.clean_text_from_number(views, 'views')
            self.scrapped_channels[chid].update({'phone_numbers': phone_numbers,
                                                 'subscriber_count': subs,
                                                 'videos_count': videos_count,
                                                 'total_views': total_views,
                                                 **found_links,
                                                 **geography})

        # Inform the success of cleaning
        self.logger.log("The scrapped channels ({}) cleaned."
                        "".format(len(self.scrapped_channels)), 'INFO')

        try:
            # Read previously scrapped_channels (cleaned)
            with open(cleaned_output_file, 'r+', encoding='utf-8') as output_file:
                prev_scrapped_channels = json.load(output_file)

            prev_scrapped_channels.update(self.scrapped_channels)

        except FileNotFoundError as e:
            prev_scrapped_channels = self.scrapped_channels

        with open(cleaned_output_file, 'w+', encoding='utf-8') as json_file:
            json.dump(prev_scrapped_channels,
                      json_file,
                      indent=3,
                      ensure_ascii=False)
            self.logger.log("The clean scrapped channels saved to {}"
                            "".format(cleaned_output_file),
                            'INFO')

    def to_pandas(self):
        """
        to_pandas
        """
        # Inform the starting of converting the channels to dataframe.
        self.logger.log("Converting the scrapped data to a pandas "
                        "dataframe ...")
        # intiate a new dictionary to save the data in.
        new_channels_data, i = {}, 0

        # Loop over all channels, and double any with mupltiple numbers.
        for index, channel_data in self.scrapped_channels.items():

            # Get all th channel's data except the phone numbers.
            new_channel_data = {'Application number': index,
                                'Application name': channel_data.get('application_name'),
                                'Channel name': channel_data.get('channel_name'),
                                'Channel ID': channel_data.get('channel_handle'),
                                'Link': channel_data.get('application_link'),
                                'Downloads': channel_data.get('downloads', None),
                                'Console': channel_data.get('console', None),
                                'Channel Link': channel_data.get('channel_link'),
                                'Telegram Channel': self.items_separator.join(channel_data.get('telegram_links')),
                                'Instagram Page': self.items_separator.join(channel_data.get('instagram_links')),
                                'Subscribers Number': channel_data.get('subscriber_count'),
                                'Videos Count': channel_data.get('videos_count'),
                                'Joined Date': channel_data.get('joined_on'),
                                'Total Views': channel_data.get('total_views'),
                                'City': channel_data.get('city'),
                                'State': channel_data.get('state'),
                                'Websites': self.items_separator.join(channel_data.get('other_links'))}

            # replace phone_numbers, if it an empty list, with ['']
            phone_numbers = channel_data.get('phone_numbers')
            if not phone_numbers:
                phone_numbers = ['']

            # Otherwise, iterate over all phone numbers, and add a new element
            # (that must used to create a row in the dataframe) for each.
            for phone_number in phone_numbers:
                new_channel_data.update({'Contact Number': phone_number})
                new_channels_data.update({i: new_channel_data.copy()})
                i += 1

        # return the dataframe.
        return pd.DataFrame.from_dict(new_channels_data, orient='index')

    def scrape(self):
        """
        scrape
        """
        # Inform starting scrapping the channels.
        self.logger.log("Start scrapping ...", 'INFO', _br=True)

        if not self._f_to_scrape_channels:
            self.logger.log("No channel to scrape.", 'INFO', _br=True)

        # start scrapping
        for chid, channel in self._f_to_scrape_channels.items():

            # get the channel name
            channel = channel.get('channel')

            # Use try except to avoid code breaking.
            self.logger.log(f"Extracting channel {chid} : {channel} ...", _br=True)
            try:

                # The link to use for searching.
                application_link = ("https://www.youtube.com/results?"
                               "search_query={}&sp=EgIQAg%253D%253D"
                               "".format(channel.replace(' ', '+')))

                # Get the results to the driver.
                self.driver.get(application_link)

                # Save the channel name and the search link.
                channel_data = {'application_name': channel,
                                'application_link': application_link}

                # Wait the visibility of the list of related channels.
                try:
                    self.long_wait.until(ec.visibility_of_element_located(
                        (By.CLASS_NAME, 'channel-link')))

                # If the time is out, check if the results is not found or
                # there is another issue.
                except Exception as e:

                    # Check if the error is raised because of there is no
                    # results to find.
                    try:
                        # NOTE: promo-title is the class that's displaying "No results found"
                        self.short_wait.until(ec.visibility_of_element_located(
                            (By.CLASS_NAME, 'promo-title')))

                        # find the element whose class name is 'promo-title'
                        result = self.driver.find_element(By.CLASS_NAME,
                                                          'promo-title')

                        # Ensure that the results == 'No results found', and
                        # if so, raise a NoResultsException exception.
                        if result.text == 'No results found':
                            raise NoResultsException("no results found four channel {}"
                                                     "".format(chid))

                        # Otherwise, raise the old exception.
                        e.message = "Channel searching failure ( Time out )"
                        raise e

                    # If the NoResultsException is raise, re-raise it to the outer exception
                    except NoResultsException as e:
                        raise e
                    
                    # If the promo-title class is not found, then the issue was not
                    # a time out.
                    except Exception as e:
                        e.message = "Time out"
                        raise e

                # If no exception is raised, then search results were found.
                # Hence, search for the list of dound channels.
                found_channels_link = self.driver.find_elements(By.CLASS_NAME,
                                                                'channel-link')

                # If the list is not empty, target the first element in it.
                if found_channels_link:

                    ######### UPDATE : AVOID YTB 404 ERROR on about pages

                    found_channel = found_channels_link[0]
                    found_channel.click()

                    show_more_locator = (By.CSS_SELECTOR, '.style-scope.ytd-channel-tagline-renderer')

                    self.long_wait.until(ec.presence_of_element_located(show_more_locator))

                    show_more_a = self.driver.find_element(*show_more_locator)

                    show_more_a.click()

                    time.sleep(0.5)

                    #####################################################

                    # Target the first channel found, and extract its link to use it
                    # as the targeted link.
                    # targeted_channel_link = (found_channels_link[0]
                    #                          .get_attribute('href'))

                    targeted_channel_link = self.driver.current_url.removesuffix('/about')

                    self.logger.log("Channel {} :: Targeting link : {}"
                                    "".format(chid, targeted_channel_link))

                    # Add this link to the channel's scrapped data.
                    channel_data.update(
                        {'channel_link': targeted_channel_link})
                    
                    # Direct the self.driver to the channel's about section.
                    # self.driver.get(targeted_channel_link + '/about')

                    try: # Extract channel's metadata ################################

                        # Locate channel's header
                        header_locator = (By.XPATH, '//div[@id="inner-header-container"]')
                        # Wait for the presence of the header.
                        self.long_wait.until(ec.presence_of_element_located(header_locator))
                        # Get the header content
                        header_container = self.driver.find_element(*header_locator)
                        
                        # Search in the header for the channel's name
                        channel_name = find_meta_description(chid, header_container,
                                                        "channel-name",
                                                        self.logger)

                        # Search in the header for the channel's subscriber count
                        subscriber_count = find_meta_description(chid, header_container,
                                                            "subscriber-count",
                                                            self.logger)
                        
                        # Search in the header for the channel's videos count
                        videos_count = find_meta_description(chid, header_container,
                                                        "videos-count",
                                                        self.logger)

                        # Search in the header for the channel's handle
                        channel_handle = find_meta_description(chid, header_container,
                                                          "channel-handle",
                                                          self.logger)
                        
                        # Add channel name to the channel's scrapped data.
                        channel_data.update({'channel_name': channel_name})
                        # Add channel's subscriber count to the channel's scrapped data.
                        channel_data.update({'subscriber_count': subscriber_count})
                        # Add channel's videos count to the channel's scrapped data.
                        channel_data.update({'videos_count': videos_count})
                        # Add channel handle to the channel's scrapped data.
                        channel_data.update({'channel_handle': channel_handle})

                    # If failed, raise an exception
                    except Exception as e:
                        # Customize the exception message
                        e.message = ("Metadata extraction failure ( Time out )"
                                     if isinstance(e, TimeoutException)
                                     else "Metadata extraction failure")
                        # Raise the exception
                        raise e
                    
                    try: # Extract channel's description ################################

                        # Locate channel's description
                        description_locator = (By.XPATH, '//div[@id="description-container"]')
                        # Wait for the presence of the description.
                        self.short_wait.until(ec.presence_of_element_located(description_locator))
                        # Get the description content
                        description = find_meta_description(chid, self.driver,
                                                       'description-container',
                                                       self.logger, 'div')
                        # Add description to the channel's scrapped data.
                        channel_data.update({'description': description})

                    except Exception as e:
                        # Customize the exception message
                        e.message = ("Description extraction failure ( Time out )"
                                     if isinstance(e, TimeoutException)
                                     else "Description extraction failure")
                        # Raise the exception
                        raise e
                    
                    try:  # Extract channel's related links ################################

                        # Locate channel's related links
                        links_locator = (By.XPATH, '//div[@id="links-container"]')
                        # Wait for the presence of the links-container
                        self.short_wait.until(ec.presence_of_element_located(links_locator))
                        # Get the links.
                        links = find_links(chid, self.driver,
                                           'links-container',
                                           self.logger)
                        # Add found links to the channel's scrapped data.
                        channel_data.update({'other_links': links})

                    except Exception as e:
                        # Customize the exception message
                        e.message = ("Links extraction failure ( Time out )"
                                     if isinstance(e, TimeoutException)
                                     else "Links extraction failure")
                        # Raise the exception
                        raise e
                    
                    try:  # Extract channel's stats ################################

                        # Locate channel's stats
                        stats_locator = (By.XPATH, '//div[@id="right-column"]')
                        # Wait for the presence of the right-column
                        self.short_wait.until(ec.presence_of_element_located(stats_locator))
                        # Get the total views and the joined date.
                        joined_on, total_views = find_stats(chid, self.driver,
                                                            'right-column',
                                                            self.logger)
                        # Add found stats to the channel's scrapped data.
                        channel_data.update({'joined_on': joined_on,
                                             'total_views': total_views})

                    except Exception as e:
                        # Customize the exception message
                        e.message = ("Stats extraction failure ( Time out )"
                                     if isinstance(e, TimeoutException)
                                     else "Stats extraction failure")
                        # Raise the exception
                        raise e
                    
                    #####################################################################################################

                # Add the final channel's data to channels_data.
                self.scrapped_channels.update({chid: channel_data})

                # Inform the success of scrapping.
                self.logger.log("Extracting the channel '{}' finished "
                                "successfully.".format(channel), 'INFO')
                
            except (MaxRetryError, ProtocolError) as e:
                # Log the error
                self.logger.log(traceback.format_exc(limit=10), 'ERROR', True)
                break


            # If any exception or error is raized, skip the channel.
            except NoResultsException as e:
                # Log a warning message to inform that no results found.
                self.logger.log("Channel '{}' is ignored : {}."
                                "".format(channel, e.message), 'WARNING')
                # Add the channels to ignored_channels channels.
                self.ignored_channels.update({chid: {'channel': channel}})
                continue

            except Exception as e:
                # Ensure the message
                if hasattr(e, 'message'):
                    msg = e.message
                else:
                    msg = type(e).__name__
                # Log the error
                self.logger.log(traceback.format_exc(limit=10), 'ERROR', True)
                # Log a warning message to inform that a TimeoutException
                # raised.
                self.logger.log("Channel '{}' is skipped : {}."
                                "".format(channel, msg, 'WARNING'))
                # Add the channels to unscrapped_channels channels.
                self.unscrapped_channels.update({chid: {'channel': channel,
                                                        'reason': msg}})

        # Close the browser.
        self.driver.quit()

        # Inform the end of scrapping.
        self.logger.log("Scrapping finished.\n", 'INFO', _br=True)


def read_unscrapped_channels(output_dir, logger) -> dict:
    """
    Read the unscrapped channels' names from unscrapped_channels.json
    """
    channels_file_name = f"{output_dir}\\unscrapped_channels.json"
    logger.log(f"Reading the channels' names from {channels_file_name}.")
    with open(channels_file_name,
              'r+', encoding='utf-8') as unscrapped_channels_file:
        unscrapped_channels: dict = json.load(unscrapped_channels_file)
    # Return the unscrapped channels names.
    return unscrapped_channels


def read_cleaned_states(output_dir, logger):
    """
    Read the cleaned cities by states from cities_by_states.json
    """
    states_file_name = f"{output_dir}\\cities_by_states.json"
    logger.log(f"Reading the states and cities from {states_file_name}.")
    with open(states_file_name,
              'r+', encoding='utf-8') as states_file:
        states: dict = json.load(states_file)
    # Return the unscrapped channels names.
    return states


def output_states_to_json(output_dir, logger):
    """
    Read states and cities from the excel file, and save
    it into a json file.

    """
    input_file_name = ('\\'.join(output_dir.split('\\')[:-1])
                       + f"\\input\\{states_input_name}")
    # Log
    logger.log(f"Reading the states and cities from {input_file_name} ...")
    states = (pd.read_excel(input_file_name, usecols=[1, 2])
              .iloc[:-2, :].applymap(str.lower)
              .rename(columns={'Name of City': 'City'}))
    states = states.groupby('State').agg(list).squeeze().to_dict()
    # Save it under the name cities_by_states.json
    output_file = f"{output_dir}\\cities_by_states.json"
    with open(output_file, 'w+', encoding='utf-8') as o_file:
        json.dump(states,
                  o_file,
                  ensure_ascii=False,
                  indent=3)
    return states


def output_channels_to_json(output_dir, logger):
    """
    Read channels names from the excel file, and save
    it into a json file that will be updated each time
    the script is ran.

    """
    # Read all the channels from the excel file.
    input_file_name = ('\\'.join(output_dir.split('\\')[:-1])
                       + f"\\input\\{input_data_name}")
    # Log
    logger.log(f"Reading the channels' names from {input_file_name} ...")
    excel_data = (pd.read_excel(input_file_name)
                  .rename(columns={'Application name': 'channel'}))
    excel_data.index = excel_data.index.astype(str)
    # Convert it to a dictionary (json)
    unscrapped_channels = excel_data.loc[:, ['channel']].to_dict('index')
    # Save it under the name unscrapped_channels.json
    output_file = f"{output_dir}\\unscrapped_channels.json"
    with open(output_file, 'w+', encoding='utf-8') as o_file:
        json.dump(unscrapped_channels,
                  o_file,
                  ensure_ascii=False,
                  indent=3)
    return unscrapped_channels


def truncate_output_directory(output_dir, logger):
    """
    Truncate the output directory and re-create the json
    file with name unscrapped_channels.json, and write in
    all the channels names.

    """
    # get all the file names in the directory
    file_names = os.listdir(output_dir)
    logger.log("Truncating the {} directory ...".format(output_dir))
    # loop through each file name and remove it
    for file_name in file_names:
        if not file_name.endswith('.log'):
            file_path = os.path.join(output_dir, file_name)
            os.remove(file_path)
    # If the directory is successfully truncated, create the json
    # file with name unscrapped_channels.json, and write in
    # all the channels names.
    channels = output_channels_to_json(output_dir, logger)
    states = output_states_to_json(output_dir, logger)
    return channels, states


def parse_arguments():
    """
    Arguments parser.
    """
    parser = argparse.ArgumentParser(description='YouTube scrapping')
    # Add restart argument.
    parser.add_argument('--restart', action='store_true',
                        help=('Indicates whether to restart the scrapping '
                              'or continue only with unscrapped channels.'))
    # Add test argument.
    parser.add_argument('--test', action='store_true',
                        help='Executes the script in test mode')
    # Add start channel argument.
    parser.add_argument('--start_with', type=int, default=None,
                        help='The index of channel to start with (used only in testing mode)')
    # Add end channel argument.
    parser.add_argument('--end_with', type=int, default=None,
                        help='The index of channel to end with (used only in testing mode)')
    # Parse the arguments.
    args = parser.parse_args()
    # Retuen them.
    return args


def run():
    """
    Execute the the script for testing some channels:

        python ./yt_scraper/locator.py --test --start_with 3 --end_with 5

    Execute the script :

        python ./yt_scraper/locator.py

    """

    args = parse_arguments()

    # Check if the script is to be run on test mode.
    is_test = True if args.test else False

    # The current directory (must be package/)
    curr_dir = os.path.dirname(__file__)
    # The directory where input data is expected to be.
    input_dir = f"{curr_dir}\\input"
    # The directory where the outputs are expected to be saved.
    output_dir = (f"{curr_dir}\\output_test"
                  if is_test
                  else f"{curr_dir}\\output")

    log_output = f"{output_dir}\\log_output_{file_name_timer()}.log"

    logger = Logger(out=log_output)

    # Initial data
    channels = None
    states = None

    # Clear the output directory if restart argument is passed.
    # NOTE: restart argument indicates the begening of scrapping,
    # and hence all the files needed to be truncated.
    if args.restart:
        channels, states = truncate_output_directory(output_dir, logger)

    # Ensure channels' names are loaded.
    if not channels:
        logger.log("Read the channels' names.\n")
        channels = read_unscrapped_channels(output_dir, logger)

    # Read the city and state names
    if not states:
        states = read_cleaned_states(output_dir, logger)

    ### NOTE: ONLY FOR TESTING ############################################
    if is_test:
        start_with = args.start_with or 0
        end_with = args.end_with or len(channels)

        channels = {str(i): channels.get(str(i))
                    for i in range(start_with, end_with)
                    if channels.get(str(i))}
    #######################################################################

    # Initiate the scrapper
    scrapper = Scrapper(to_scrape_channels=channels,
                        cities_by_states=states,
                        logger=logger)

    # return

    # Start scrapping
    scrapper.scrape()

    # Save unscrapped channels it to a json file.
    scrapper.save_unscrapped_channels(output_dir)
    
    # Save channels with no results it to a json file.
    scrapper.save_ignored_channels(output_dir)

    # Save unscrapped channels it to a json file.
    scrapper.save_scrapped_channels(output_dir)

    # Convert the cleaned data into a pandas dataframe.
    channels_dataframe = scrapper.to_pandas()

    # Save the dataframe into excel file.
    xl_output_file = f"{output_dir}\\output.xlsx"

    # First, check if current run is the starting one,
    # i.g. the file is already exists, and the new results
    # must be concatenated to it.
    if not args.restart:
        # If so, read the file.
        prev_channels_dataframe = pd.read_excel(xl_output_file,
                                                sheet_name='main')
        # And then concatenate it with the new results.
        channels_dataframe = pd.concat([prev_channels_dataframe,
                                        channels_dataframe])
    # Save the final results to the file.
    channels_dataframe.to_excel(xl_output_file,
                                sheet_name='main',
                                index=False)

    # Inform the success of saving to excel.
    logger.log("The cleaned dataframe saved to {}"
               "".format(xl_output_file), 'INFO')


if __name__ == '__main__':
    run()
