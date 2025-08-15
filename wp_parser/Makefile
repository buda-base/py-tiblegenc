CXX = g++
CXXFLAGS = -O2 -std=c++11 -Wall -Wextra
PKG = libwpd-0.10 librevenge-0.0

PC_CFLAGS := $(shell pkg-config --cflags $(PKG) 2>/dev/null)
PC_LIBS   := $(shell pkg-config --libs   $(PKG) 2>/dev/null)

TARGET = wp_raw_extract
SRC = wp_raw_extract.cpp

all: $(TARGET)

$(TARGET): $(SRC)
	$(CXX) $(CXXFLAGS) $(PC_CFLAGS) -o $(TARGET) $(SRC) $(PC_LIBS)

clean:
	$(RM) $(TARGET)
	$(RM) $(TARGET)
