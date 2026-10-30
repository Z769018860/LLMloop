/* Local integer union view: compiler layout + little-endian x86 contract.
 * Only full-word writes and initialized scalar reads are admitted.
 */
typedef union {
  unsigned long long word;
  struct {
    unsigned int low;
    int high;
  } parts;
} Word;

int entry(unsigned long long n) {
  Word view;
  view.word = n;
  return view.parts.high;
}
