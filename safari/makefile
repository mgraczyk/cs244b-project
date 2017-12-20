TARGET = safari-server
LIBS = -lm
CXX = g++
CXXFLAGS = -Wall -Werror --std=c++1z -fdata-sections -ffunction-sections
LINKFLAGS = -Wall -lcapnp -lkj -lcapnp-json

ifeq ($(DEBUG),1)
  CXXFLAGS+=-g -O0 -DDEBUG=1
else
  CXXFLAGS+=-O3 -DNDEBUG=1 -flto
endif
MAKEFLAGS += --no-builtin-rules

.SUFFIXES:
.PHONY: default all clean capnp

default: $(TARGET)
all: default

OBJECTS = $(patsubst %.cc, %.o, $(wildcard *.cc))
HEADERS = $(wildcard *.h)

%.o: %.cc $(HEADERS)
	$(CXX) $(CXXFLAGS) -c $< -o $@

%.capnp.cc %.capnp.h: %.capnp
	capnp compile $< -oc++
	mv $*.capnp.c++ $*.capnp.cc


.PRECIOUS: $(TARGET) $(OBJECTS) types.capnp.h types.capnp.cc

$(TARGET): types.capnp.o $(OBJECTS)
	$(CXX) $^ $(LINKFLAGS) $(LIBS) -o $@

clean:
	-rm -f *.o
	-rm -f $(TARGET)
	-rm -f *.capnp.*
