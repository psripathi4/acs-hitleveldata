import logging
import unittest
from unittest.mock import patch
from io import BytesIO
from botocore.exceptions import ClientError
from botocore.response import StreamingBody
from process_hit_level_data import lambda_function

logger = logging.getLogger()
logger.setLevel(logging.INFO)


class TestGetRevenue(unittest.TestCase):
    patch_prefix = 'process_hit_level_data.lambda_function'
    product_list_str_valid = 'Computers;HP Pavillion;1;1000;200|201,Office Supplies;Red Folders;4;4.00;205|206|207'
    product_list_str_invalid_rev = 'Computers;HP Pavillion;1;BAD_REV;200|201'
    product_list_str_invalid_inp = 'Computers;HP Pavillion;1;200'

    def test_get_revenue_success(self):
        response = lambda_function.ProcessHitLevelData.get_revenue(
            self, self.product_list_str_valid)
        self.assertEqual(response, 1004.0)

    @patch(f'{patch_prefix}.logger')
    def test_get_revenue_bad_rev_value(self, mocked_logger):
        response = lambda_function.ProcessHitLevelData.get_revenue(
            self, self.product_list_str_invalid_rev)
        self.assertEqual(response, None)
        mocked_logger.error.assert_called_once()

    def test_get_revenue_invalid_inp(self):
        response = lambda_function.ProcessHitLevelData.get_revenue(
            self, self.product_list_str_invalid_inp)
        self.assertEqual(response, None)


class ValidateKeywordExtraction(unittest.TestCase):
    url_valid1 = 'http://www.google.com/search?hl=en&client=firefox-a&rls=org.mozilla%3Aen-US%3Aofficial&hs=ZzP&q=Ipod&aq=f&oq=&aqi='
    url_valid2 = 'http://www.bing.com/search?q=Zune+player&go=&form=QBLH&qs=n'

    def test_extract_keyword_success_google(self):
        response = lambda_function.ProcessHitLevelData.extract_keyword(
            self, 'google', self.url_valid1)
        self.assertEqual(response, 'ipod')

    def test_extract_keyword_success_bing(self):
        response = lambda_function.ProcessHitLevelData.extract_keyword(
            self, 'bing', self.url_valid2)
        self.assertEqual(response, 'zune player')


class ValidateS3UploadResults(unittest.TestCase):
    patch_prefix = 'process_hit_level_data.lambda_function'
    s3_bucket = 'test-s3-bucket'
    revenue = {'bing.com#zune': 250.0, 'google.com#ipod': 480.0}
    s3_upload_fail_resp = {'Error': {'Code': 'NoSuchBucket', 'Message': 'An error occurred (NoSuchBucket) when calling the PutObject operation: The specified bucket does not exist'}, 'ResponseMetadata': {
        'HTTPStatusCode': 200}}

    @patch(f'{patch_prefix}.boto3')
    def test_push_output_s3_success(self, mocked_boto):

        s3_client = mocked_boto.client('s3')
        s3_client.upload_file.return_value = True

        response = lambda_function.ProcessHitLevelData.publish_output_to_s3(
            self, self.s3_bucket)
        self.assertEqual(type(response), dict)
        self.assertEqual(response['success'], True)

    @patch(f'{patch_prefix}.boto3')
    def test_push_output_s3_fail(self, mocked_boto):

        s3_client = mocked_boto.client('s3')
        s3_client.upload_file.side_effect = ClientError(
            self.s3_upload_fail_resp, operation_name='upload_file')

        response = lambda_function.ProcessHitLevelData.publish_output_to_s3(
            self, self.s3_bucket)
        self.assertEqual(type(response), dict)
        self.assertEqual(response['success'], False)
        self.assertEqual(response['response']['Error']['Code'], 'NoSuchBucket')


class ValidateCalculatingRevenue(unittest.TestCase):
    patch_prefix = 'process_hit_level_data.lambda_function'
    record = {'eventSource': 'aws:s3', 'eventName': 'ObjectCreated:Put', 's3': {'bucket': {
        'name': 'acs-hit-level-data-store1', 'arn': 'arn:aws:s3:::acs-hit-level-data-store1'}, 'object': {'key': 'hit-level-data/data.tsv'}}}
    s3_get_obj_fail_resp = {'Error': {'Code': 'BadRequest', 'Message': 'The bucket is in a transitional state because of a previous deletion attempt. Try again later.'}, 'ResponseMetadata': {
        'HTTPStatusCode': 400}}
    inp_records = 'hit_time_gmt\tdate_time\tuser_agent\tip\tevent_list\tgeo_city\tgeo_region\tgeo_country\tpagename\tpage_url\tproduct_list\treferrer\n\
1254033280\t2009-09-27 06:34:40\tMozilla\t67.98.123.1\t\tSalem\tOR\tUS\tHome\thttp://www.esshopzilla.com\t\thttp://www.google.com/search?hl=en&client=firefox-a&rls=org.mozilla%3Aen-US%3Aofficial&hs=ZzP&q=Ipod&aq=f&oq=&aqi=\n\
1254033379\t2009-09-27 06:36:19\tMozilla\t23.8.61.21\t2\tRochester\tNY\tUS\tZune - 32 GB\thttp://www.esshopzilla.com/product/?pid=asfe13\tElectronics;Zune - 328GB;1;;\thttp://www.bing.com/search?q=Zune&go=&form=QBLH&qs=n\n\
1254033478\t2009-09-27 06:37:58\tMozilla\t112.33.98.231\t\tSalt Lake City\tUT\tUS\tHome\thttp://www.esshopzilla.com\t\thttp://search.yahoo.com/search?p=cd+player&toggle=1&cop=mss&ei=UTF-8&fr=yfp-t-701\n\
1254033577\t2009-09-27 06:39:37\tMozilla\t44.12.96.2\t\tDuncan\tOK\tUS\tHot Buys\thttp://www.esshopzilla.com/hotbuys/\t\thttp://www.google.com/search?hl=en&client=firefox-a&rls=org.mozilla%3Aen-US%3Aofficial&hs=Zk5&q=ipod&aq=f&oq=&aqi=g-p1g9\n\
1254033676\t2009-09-27 06:41:16\tMozilla\t67.98.123.1\t\tSalem\tOR\tUS\tSearch Results\thttp://www.esshopzilla.com/search/?k=Ipod\t\thttp://www.esshopzilla.com\n\
1254034677\t2009-09-27 06:41:16\tMozilla\n\
1254033775\t2009-09-27 06:42:55\tMozilla\t23.8.61.21\t12\tRochester\tNY\tUS\tShopping Cart\thttp://www.esshopzilla.com/cart/\t\thttp://www.esshopzilla.com/product/?pid=asfe13\n\
1254033874\t2009-09-27 06:44:34\tMozilla\t44.12.96.2\t2\tDuncan\tOK\tUS\tIpod - Nano - 8 GB\thttp://www.esshopzilla.com/product/?pid=as32213\tElectronics;Ipod - Nano - 8GB;1;;\thttp://www.esshopzilla.com/hotbuys/\n\
1254033973\t2009-09-27 06:46:13\tMozilla\t67.98.123.1\t2\tSalem\tOR\tUS\tIpod - Nano - 8 GB\thttp://www.esshopzilla.com/product/?pid=as32213\tElectronics;Ipod - Nano - 8GB;1;;\thttp://www.esshopzilla.com/search/?k=Ipod\n\
1254033974\t2009-09-27 06:36:19\tMozilla\t23.8.61.21\t2\tRochester\tNY\tUS\tZune - 32 GB\thttp://www.esshopzilla.com/product/?pid=asfe13\tElectronics;Zune - 328GB;1;;\thttp://www.bing.com/search?q=Zune+Discounted&go=&form=QBLH&qs=n\n\
1254034072\t2009-09-27 06:47:52\tMozilla\t23.8.61.21\t11\tRochester\tNY\tUS\tOrder Checkout Details\thttps://www.esshopzilla.com/checkout/\t\thttp://www.esshopzilla.com/cart/\n\
1254034171\t2009-09-27 06:49:31\tMozilla\t44.12.96.2\t12\tDuncan\tOK\tUS\tShopping Cart\thttp://www.esshopzilla.com/cart/\t\thttp://www.esshopzilla.com/product/?pid=as23233\n\
1254034270\t2009-09-27 06:51:10\tMozilla\t67.98.123.1\t\tSalem\tOR\tUS\tSearch Results\thttp://www.esshopzilla.com/search/?k=Ipod\t\thttp://www.esshopzilla.com/product/?pid=as32213\n\
1254034369\t2009-09-27 06:52:49\tMozilla\t23.8.61.21\t\tRochester\tNY\tUS\tOrder Confirmation\thttps://www.esshopzilla.com/checkout/?a=confirm\t\thttps://www.esshopzilla.com/checkout/\n\
1254034468\t2009-09-27 06:54:28\tMozilla\t44.12.96.2\t11\tDuncan\tOK\tUS\tOrder Checkout Details\thttps://www.esshopzilla.com/checkout/\t\thttp://www.esshopzilla.com/cart/\n\
1254034567\t2009-09-27 06:56:07\tMozilla\t67.98.123.1\t2\tSalem\tOR\tUS\tIpod - Touch - 32 GB\thttp://www.esshopzilla.com/product/?pid=as23233\tElectronics;Ipod - Touch - 32GB;1;;\thttp://www.esshopzilla.com/search/?k=Ipod\n\
1254034666\t2009-09-27 06:57:46\tMozilla\t23.8.61.21\t1\tRochester\tNY\tUS\tOrder Complete\thttps://www.esshopzilla.com/checkout/?a=complete\tElectronics;Zune - 32GB;1;250;\thttps://www.esshopzilla.com/checkout/?a=confirm\n\
1254034765\t2009-09-27 06:59:25\tMozilla\t44.12.96.2\t\tDuncan\tOK\tUS\tOrder Confirmation\thttps://www.esshopzilla.com/checkout/?a=confirm\t\thttps://www.esshopzilla.com/checkout/\n\
1254034864\t2009-09-27 07:01:04\tMozilla\t67.98.123.1\t12\tSalem\tOR\tUS\tShopping Cart\thttp://www.esshopzilla.com/cart/\t\thttp://www.esshopzilla.com/product/?pid=as23233\n\
1254034963\t2009-09-27 07:02:43\tMozilla\t44.12.96.2\t1\tDuncan\tOK\tUS\tOrder Complete\thttps://www.esshopzilla.com/checkout/?a=complete\tElectronics;Ipod - Nano - 8GB;1;BAD_REVENUE;\thttps://www.esshopzilla.com/checkout/?a=confirm\n\
1254034963\t2009-09-27 07:02:43\tMozilla\t44.12.96.2\t1\tDuncan\tOK\tUS\tOrder Complete\thttps://www.esshopzilla.com/checkout/?a=complete\tElectronics;Ipod - Nano - 8GB;1;190;\thttps://www.esshopzilla.com/checkout/?a=confirm\n\
1254035062\t2009-09-27 07:04:22\tMozilla\t67.98.123.1\t11\tSalem\tOR\tUS\tOrder Checkout Details\thttps://www.esshopzilla.com/checkout/\t\thttp://www.esshopzilla.com/cart/\n\
1254035161\t2009-09-27 07:06:01\tMozilla\t67.98.123.1\t\tSalem\tOR\tUS\tOrder Confirmation\thttps://www.esshopzilla.com/checkout/?a=confirm\t\thttps://www.esshopzilla.com/checkout/\n\
1254035260\t2009-09-27 07:07:40\tMozilla\t67.98.123.1\t1\tSalem\tOR\tUS\tOrder Complete\thttps://www.esshopzilla.com/checkout/?a=complete\tElectronics;Ipod - Touch - 32GB;1;290;\thttps://www.esshopzilla.com/checkout/?a=confirm'

    @patch(f'{patch_prefix}.logger')
    @patch(f'{patch_prefix}.boto3')
    def test_calculate_revenue_fail_s3_read(self, mocked_boto, mocked_logger):
        s3_client = mocked_boto.client('s3')
        s3_client.get_object.side_effect = ClientError(
            self.s3_get_obj_fail_resp, operation_name='get_object')

        obj = lambda_function.ProcessHitLevelData()
        response = obj.calculate_revenue_off_search_engines(self.record)
        self.assertEqual(type(response), bool)
        self.assertEqual(response, False)
        mocked_logger.error.assert_called_once()

    @patch(f'{patch_prefix}.ProcessHitLevelData.publish_output_to_s3', return_value={'success': True})
    @patch(f'{patch_prefix}.ProcessHitLevelData.get_revenue', side_effect=[250.0, 190.0, 290.0])
    @patch(f'{patch_prefix}.ProcessHitLevelData.extract_keyword', side_effect=['ipod', 'zune', 'cd player', 'ipod', 'zune discounted'])
    @patch(f'{patch_prefix}.logger')
    @patch(f'{patch_prefix}.boto3')
    def test_calculate_revenue_success(self, mocked_boto, mocked_logger, mocked_extract_keyword, mocked_get_rev, mocked_s3_upload):

        s3_client = mocked_boto.client('s3')
        body_encoded = self.inp_records.encode("utf-8")
        streaming_body = StreamingBody(
            BytesIO(body_encoded),
            len(body_encoded)
        )
        s3_client.get_object.return_value = {'Body': streaming_body}

        obj = lambda_function.ProcessHitLevelData()
        response = obj.calculate_revenue_off_search_engines(self.record)
        self.assertEqual(type(response), bool)
        self.assertEqual(response, True)


class ValidateLambdaHandler(unittest.TestCase):
    patch_prefix = 'process_hit_level_data.lambda_function'
    event = {'Records': [{'eventSource': 'aws:s3', 'eventName': 'ObjectCreated:Put', 's3': {'bucket': {
        'name': 'acs-hit-level-data-store1', 'arn': 'arn:aws:s3:::acs-hit-level-data-store1'}, 'object': {'key': 'hit-level-data/data.tsv'}}}]}
    context = {}

    @patch(f'{patch_prefix}.ProcessHitLevelData.publish_output_to_s3', return_value={'success': True})
    @patch(f'{patch_prefix}.ProcessHitLevelData.calculate_revenue_off_search_engines', return_value=True)
    def test_lambda_handler_processing_success(self, mocked_calc_rev_func_call, mocked_s3_publish_func_call):

        response = lambda_function.lambda_handler(self.event, self.context)
        self.assertEqual(type(response), list)
        self.assertEqual(
            response[0]['hit-level-data/data.tsv']['success'], True)

    @patch(f'{patch_prefix}.ProcessHitLevelData.calculate_revenue_off_search_engines', return_value=False)
    def test_lambda_handler_no_rev_data_found(self, mocked_calc_rev_func_call):

        response = lambda_function.lambda_handler(self.event, self.context)
        self.assertEqual(type(response), list)
        self.assertEqual(
            response[0]['hit-level-data/data.tsv'], 'No revenue data found')
