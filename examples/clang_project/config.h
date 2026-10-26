#ifndef LLMLOOP_DEMO_CONFIG_H
#define LLMLOOP_DEMO_CONFIG_H
#define STEP 2
typedef struct Node { unsigned char value; struct Node *next; } Node;
struct __attribute__((packed)) Packed { char tag; int count; };
#endif
