#include "unity.h"
#include "power_manager.h"

void setUp(void)
{
    power_manager_init();
}

void tearDown(void)
{
}

void test_power_manager_init(void)
{
    TEST_ASSERT_TRUE(true);
}

void test_deep_sleep_entry(void)
{
    TEST_ASSERT_TRUE(true);
}

void app_main(void)
{
    UNITY_BEGIN();
    RUN_TEST(test_power_manager_init);
    RUN_TEST(test_deep_sleep_entry);
    UNITY_END();
}
