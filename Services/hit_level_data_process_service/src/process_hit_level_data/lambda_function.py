import csv
import boto3
import logging
from io import StringIO
from datetime import date
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def lambda_handler(event: dict, context: dict) -> dict:
    """
    Lambda handler to process the incoming event payload
    :param event: Lambda event payload
    :param context: context object
    :return: dict - A response object by the s3 prefix in the event and its process status
    """
    final_response = []

    logger.info(f'Incoming event - {event}')

    for event_record in event['Records']:

        lambda_executor = ProcessHitLevelData()
        rev_resp = lambda_executor.calculate_revenue_off_search_engines(
            event_record)
        if rev_resp:
            # Move the revenue's result to tab spaced file and upload to S3
            response = lambda_executor.publish_output_to_s3(
                event_record['s3']['bucket']['name'])
        else:
            response = 'No revenue data found'

        final_response.append({event_record['s3']['object']['key']: response})

    return final_response


class ProcessHitLevelData:
    def __init__(self) -> None:
        self.activity = {}
        self.revenue = {}
        self.grief = []

    def get_revenue(self, product_list: str) -> float:
        """
        Helper function to calculate the total self.revenue of the products purchased.

        :param product_list: comma delimited list of products with a semi-colon delimited list of attributes for each product
        :return: float - A response object by the s3 prefix in the event and its process status
        """

        total_rev = 0
        orders = product_list.split(',')

        for item_detail in orders:

            item_detail = item_detail.split(';')

            if len(item_detail) == 5:
                try:
                    total_rev += float(item_detail[-2])
                except ValueError:
                    logger.error(f'Bad product_list - {orders}')
                    return None
            else:
                return None

        return total_rev

    def extract_keyword(self, domain: str, url: str) -> str:
        """
        Helper function to extract the search keyword(s) from referrer url

        :param domain: The domain of the referrer
        :param url: The referrer URL
        :return: str - Extracted keyword from url if found, else None
        """

        keyword = None

        if domain == 'google':
            start = url.index('&q=') + 3
            end = url[start:].index('&')
            keyword = url[start:(start+end)]
            # Add spaces to multi-word search string
            keyword = keyword.replace('+', ' ').lower()

        elif domain in ['yahoo', 'bing', 'duckduckgo', 'yandex']:
            keyword = url.split('&')[0].split('=')[-1]
            # Add spaces to multi-word search string
            keyword = keyword.replace('+', ' ').lower()

        return keyword

    def publish_output_to_s3(self, s3_bucket: str) -> dict:
        """
        Helper function to process the self.revenue object in sorted order and publish the output file to S3

        :param s3_bucket: The s3 bucket name
        :return: dict - S3 upload resonse
        """

        today = str(date.today())
        file_name = f'{today}_SearchKeywordPerformance'

        with open(f'/tmp/{file_name}.tab', 'wb') as fout:

            # Adding header
            fout.write(
                'Search Engine Domain\tSearch Keyword\tRevenue\n'.encode())

            for item in sorted(self.revenue.items(), key=lambda x: x[1], reverse=True):
                domain, keyword = item[0].split('#')
                line = f"{domain}\t{keyword}\t{item[1]}\n"
                fout.write(line.encode())

        # Upload the file
        s3_client = boto3.client('s3')
        try:
            s3_client.upload_file(
                f'/tmp/{file_name}.tab', s3_bucket, f'hit-level-data/output/{file_name}.tab')
            response = {'success': True}
        except ClientError as ce:
            logger.error(ce)
            response = {'success': False, 'response': ce.response}

        return response

    def calculate_revenue_off_search_engines(self, record: dict) -> bool:
        """
        Function to calculate the self.revenue by processing the incoming tsv file.

        :param record: The S3 ObjectCreated:Put event record
        :return: bool - True/False if the file was processed successfully
        """

        s3_bucket = record['s3']['bucket']['name']
        s3_prefix = record['s3']['object']['key']

        try:
            s3 = boto3.client('s3')
            obj = s3.get_object(Bucket=s3_bucket, Key=s3_prefix)
            data = obj['Body'].read().decode('utf-8')
            reader = csv.reader(StringIO(data), delimiter='\t')
            next(reader)    # Skipping header

        except ClientError as ce:
            logger.error(ce)
            return False

        else:
            for row in reader:
                try:
                    ip = row[3]
                    website = row[-1].split('/')[2].split('.')
                    domain, suffix = website[1], website[2]

                    if domain != 'esshopzilla':
                        keyword = keyword = self.extract_keyword(
                            domain, row[-1])

                    if ip not in self.activity:

                        if domain != 'esshopzilla':
                            if keyword is None:
                                # Error capturing search keyword from URL
                                self.grief.append(row)
                            else:
                                self.activity[ip] = {
                                    row[0]: f'{domain}.{suffix}#{keyword}'}
                    else:
                        event = row[4]  # Get the event

                        # Only calculate self.revenue if a purchase has been made
                        if domain == 'esshopzilla':
                            if event == '1':
                                hittimegmt = sorted(
                                    self.activity[ip].keys())[-1]
                                dom_key = self.activity[ip][hittimegmt]

                                prod_list_rev = self.get_revenue(row[10])

                                if prod_list_rev is not None:

                                    # If domain#keyword already exists, add it to the total self.revenue
                                    if dom_key in self.revenue:
                                        self.revenue[dom_key] += prod_list_rev
                                        del self.activity[ip][hittimegmt]
                                    else:
                                        # If new domain#keyword, add it to self.revenue
                                        self.revenue[dom_key] = prod_list_rev
                                        del self.activity[ip][hittimegmt]

                                    # Remove the IP from the self.activity, when all purchase events are processed (if available)
                                    if len(self.activity[ip]) == 0:
                                        del self.activity[ip]
                                else:
                                    # Invalid self.revenue in product_list
                                    self.grief.append(row)
                        else:
                            self.activity[ip][row[0]
                                              ] = f'{domain}.{suffix}#{keyword}'

                except Exception as ex:
                    logger.error(ex)
                    self.grief.append(row)
                    continue

            return len(self.revenue) != 0
