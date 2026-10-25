int cfg_heap(int n, int select) {
    int *saved = 0;
    {
        int *temporary = calloc(n, sizeof(int));
        if (!temporary) {
            return -1;
        }
        saved = temporary;
    }
    int i = 0;
    int total = 0;
    do {
        switch ((i + select) % 3) {
            case 0: saved[i] = i + 1; break;
            case 1: saved[i] = 2 * (i + 1); break;
            default: saved[i] = 3 * (i + 1);
        }
        total += saved[i];
        i++;
        if (i == n) {
            goto done;
        }
    } while (i < n);
    done:
    free(saved);
    return total;
}
