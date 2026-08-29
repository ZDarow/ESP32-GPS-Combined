idf_component_register(SRCS "test_nmea_parser.c" "test_gps_ring_buffer.c" "test_power_manager.c"
                      INCLUDE_DIRS "."
                      REQUIRES nmea_parser gps_ring_buffer power_manager unity)
