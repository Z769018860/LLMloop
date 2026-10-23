int loop(int n) {
    int p=0;
    int i=0;
    int x=0;
    while (i<n) {
        if (p==0) {
            x=x+1;
        } else {
            x=x+2;
        }
        p=1-p;
        i=i+1;
    }
    return x;
}
