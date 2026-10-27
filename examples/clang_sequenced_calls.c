static int step(int n) { return n + 1; }
static int twice(int n) { return n * 2; }
static int add(int x, int y) { return x + y; }

static int test(int *counter, int i, int n) {
    counter[0] += 1;
    return i < n;
}

static int bump(int *counter, int amount) {
    counter[0] += amount;
    return counter[0];
}

int entry(int n) {
    int counter[1] = {0};
    int total = 0;
    for (int i = 0; test(counter, i, n); i = step(i)) {
        if (i == 1) { continue; }
        total += i;
    }
    int selected = n ? bump(counter, 3) : bump(counter, 5);
    int enabled = n && bump(counter, 7);
    int nested = add(step(n), twice(n));
    return total + selected + enabled + nested + counter[0];
}
