int **make_table(int n) {
    int **table = malloc(2 * sizeof(int *));
    if (!table) return 0;
    int *values = calloc(n, sizeof(int));
    if (!values) {
        free(table);
        return 0;
    }
    values[0] = n;
    table[0] = values;
    table[1] = 0;
    return table;
}
int read_table(int **table) {
    int *values = table[0];
    return values[0];
}
void dispose_table(int **table) {
    int *values = table[0];
    free(values);
    free(table);
}
int pointer_cells(int n) {
    int **table = make_table(n);
    if (!table) return -1;
    int result = read_table(table);
    dispose_table(table);
    return result;
}
