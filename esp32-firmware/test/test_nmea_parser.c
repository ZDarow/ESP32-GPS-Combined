#include "unity.h"
#include "nmea_parser.h"

void setUp(void)
{
    nmea_parser_init();
}

void tearDown(void)
{
}

void test_nmea_parser_feed_valid_rmc(void)
{
    gnss_fix_t fix = {0};
    const char *sentence = "$GPRMC,120000,A,4807.038,N,01131.000,E,0.0,0.0,010124,,,A*77";
    bool result = nmea_parser_feed(sentence, strlen(sentence), &fix);
    TEST_ASSERT_TRUE(result);
    TEST_ASSERT_TRUE(fix.valid);
    TEST_ASSERT_EQUAL(GNSS_FIX_2D, fix.type);
}

void test_nmea_parser_feed_invalid_checksum(void)
{
    gnss_fix_t fix = {0};
    const char *sentence = "$GPRMC,120000,A,4807.038,N,01131.000,E,0.0,0.0,010124,,,A*00";
    bool result = nmea_parser_feed(sentence, strlen(sentence), &fix);
    TEST_ASSERT_FALSE(result);
}

void test_nmea_parser_feed_no_fix(void)
{
    gnss_fix_t fix = {0};
    const char *sentence = "$GPRMC,120000,V,4807.038,N,01131.000,E,0.0,0.0,010124,,,A*77";
    bool result = nmea_parser_feed(sentence, strlen(sentence), &fix);
    TEST_ASSERT_TRUE(result);
    TEST_ASSERT_FALSE(fix.valid);
}

void test_nmea_parser_feed_empty(void)
{
    gnss_fix_t fix = {0};
    const char *sentence = "";
    bool result = nmea_parser_feed(sentence, 0, &fix);
    TEST_ASSERT_FALSE(result);
}

void app_main(void)
{
    UNITY_BEGIN();
    RUN_TEST(test_nmea_parser_feed_valid_rmc);
    RUN_TEST(test_nmea_parser_feed_invalid_checksum);
    RUN_TEST(test_nmea_parser_feed_no_fix);
    RUN_TEST(test_nmea_parser_feed_empty);
    UNITY_END();
}
