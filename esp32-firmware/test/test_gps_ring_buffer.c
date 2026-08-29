#include "unity.h"
#include "gps_ring_buffer.h"

static gps_ring_buffer_t s_rb;

void setUp(void)
{
    gps_ring_buffer_init(&s_rb);
}

void tearDown(void)
{
    gps_ring_buffer_clear(&s_rb);
}

void test_ring_buffer_write_and_read(void)
{
    const uint8_t data[] = "Hello";
    size_t written = gps_ring_buffer_write(&s_rb, data, sizeof(data) - 1);
    TEST_ASSERT_EQUAL(sizeof(data) - 1, written);

    uint8_t read_buf[10] = {0};
    size_t read = gps_ring_buffer_read(&s_rb, read_buf, sizeof(read_buf) - 1);
    TEST_ASSERT_EQUAL(sizeof(data) - 1, read);
    TEST_ASSERT_EQUAL_UINT8_ARRAY(data, read_buf, sizeof(data) - 1);
}

void test_ring_buffer_available(void)
{
    const uint8_t data[] = "Test";
    gps_ring_buffer_write(&s_rb, data, sizeof(data) - 1);
    TEST_ASSERT_EQUAL(sizeof(data) - 1, gps_ring_buffer_available(&s_rb));
}

void test_ring_buffer_overflow(void)
{
    TEST_ASSERT_FALSE(gps_ring_buffer_has_overflowed(&s_rb));
}

void test_ring_buffer_clear(void)
{
    const uint8_t data[] = "Data";
    gps_ring_buffer_write(&s_rb, data, sizeof(data) - 1);
    gps_ring_buffer_clear(&s_rb);
    TEST_ASSERT_EQUAL(0, gps_ring_buffer_available(&s_rb));
}

void app_main(void)
{
    UNITY_BEGIN();
    RUN_TEST(test_ring_buffer_write_and_read);
    RUN_TEST(test_ring_buffer_available);
    RUN_TEST(test_ring_buffer_overflow);
    RUN_TEST(test_ring_buffer_clear);
    UNITY_END();
}
