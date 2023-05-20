
### Runing's instructions :
---

- Extract (unzip the package.zip file) into a directory

- Change Directory to the package directory

- Run the script using : `python3 locator.py --restart`

- If the runing ends, not matter what the results are, explore the log file : `package/output/log_output_YYYYmmdd_HHMMSS.log`. ( `YYYYmmdd_HHMMSS` is the time of starting the execution )

- In the log file, you may see some error and warning of scrapping failure. If you do, please explore the file `package/output/unscrapped_channels.json` to figure out what channels were not successfully scrapped, and the file `package/output/ignored_channels.json` to find out the channels that were ignored because no results found when searching the application name.

- Generaly, there are two reasons, one is `'TimeoutException'` that may due to the unstable Internet connection, and the second is `'NoResultsFound'` that may due to the unavailability of the results.

- In case there is no channel unscrapped because of the `'TimeoutException'` exception, CONGRATS, the sccrapping went 100% as expected. In other case, you can re-run the script again to try continuing the scrapping. Please use the command `python3 locator.py` for re-runing the script.

### How I can explore the results ?
---

In general, the results were saved three times, in defferent formats :

- `package/output/uncleaned_scrapped_channels.json` :

    In this file, the data were saved as it's scrapped, with out any modification.

    The elements that were saved in this file are :

    - application_name : `Unique Civil`
    - application_link : `https://www.youtube.com/results?search_query=Unique+Civil&sp=EgIQAg%253D%253D`
    - channel_link : `https://www.youtube.com/@UniqueCivil`
    - channel_handle : `@UniqueCivil`
    - channel_name : `Unique Civil`
    - subscribers_count : `34.7K subscribers`
    - videos_count : `336 videos`
    - description : `Description\nHey, guys welcome to the unique civil family ...`
    - other_links : `[...]`
    - joined_on : `Dec 22, 2020`
    - total_views : `893,591 views`
    <br><br>


- `package/output/cleaned_scrapped_channels.json` :

    In this file, the data is the same as in the previous file, but cleaned and prepocessed.

    The elements that were saved in this file are :

    - application_name : `Unique Civil`
    - application_link : `https://www.youtube.com/results?search_query=Unique+Civil&sp=EgIQAg%253D%253D`
    - channel_link : `https://www.youtube.com/@UniqueCivil`
    - channel_handle : `@UniqueCivil`
    - channel_name : `Unique Civil`
    - subscribers_count : `34700`
    - videos_count : `336`
    - description : `Description\nHey, guys welcome to the unique civil family ...`
    - other_links : `[..., https://www.facebook.com/uniquecivillearn/, https://www.linkedin.com/company/13626211/admin/", ...]`
    - phone_numbers : `[ 9792621121 ]`
    - telegram_links : `[]`
    - instagram_links : `[ https://www.instagram.com/ ]`
    - city : ` `
    - state : ` `
    - joined_on : `Dec 22, 2020`
    - total_views : `893591`

- `package/output/data_output.xlsx` :

    In this file, the data is the same as in the previous file, but structured and a table format.

    In adition to the elements in `package/output/cleaned_scrapped_channels.json`, it contains also the `'Application number'` element (column) that identifies each channels. You can notice that there are multiple duplicated channels with different phone numbers, this is the reason why this additional element were added.


