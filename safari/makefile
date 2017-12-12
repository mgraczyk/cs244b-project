TARGET = safari-server
LIBS = -lm
CXX = g++
CXXFLAGS = -Wall -Werror --std=c++1z
LINKFLAGS = -Wall

ifeq ($(DEBUG),1)
  CXXFLAGS+=-g -O0 -DDEBUG=1
else
  CXXFLAGS+=-O3 -DNDEBUG=1
endif

.PHONY: default all clean

default: $(TARGET)
all: default

OBJECTS = $(patsubst %.cc, %.o, $(wildcard *.cc))
HEADERS = $(wildcard *.h)

%.o: %.cc $(HEADERS)
	$(CXX) $(CXXFLAGS) -c $< -o $@

.PRECIOUS: $(TARGET) $(OBJECTS)

$(TARGET): $(OBJECTS)
	$(CXX) $(OBJECTS) $(LINKFLAGS) $(LIBS) -o $@

clean:
	-rm -f *.o
	-rm -f $(TARGET)
