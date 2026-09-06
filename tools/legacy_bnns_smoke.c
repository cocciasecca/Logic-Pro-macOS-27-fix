#include <dlfcn.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

typedef void *(*options_create_fn)(void);
typedef void (*options_single_fn)(void *, int);
typedef void (*options_optim_fn)(void *, uint32_t);
typedef void *(*compile_fn)(uint32_t, const char *, const char *, void *);
typedef size_t (*get_size_fn)(void *);
typedef size_t (*count_fn)(void *, const char *);
typedef int (*names_fn)(void *, const char *, size_t, const char **);
typedef size_t (*workspace_fn)(void *);
typedef int (*ready_fn)(void);

static void *required(void *handle, const char *name) {
    void *symbol = dlsym(handle, name);
    if (!symbol) {
        fprintf(stderr, "missing %s\n", name);
        exit(2);
    }
    return symbol;
}

int main(int argc, char **argv) {
    if (argc != 3) {
        fprintf(stderr, "usage: legacy_bnns_smoke BNNSCompat.dylib model.mil\n");
        return 64;
    }
    void *handle = dlopen(argv[1], RTLD_NOW | RTLD_LOCAL);
    if (!handle) {
        fprintf(stderr, "dlopen failed: %s\n", dlerror());
        return 1;
    }
    ready_fn ready = (ready_fn)required(handle, "BNNSCompatReady");
    if (!ready()) {
        fprintf(stderr, "BNNSCompatReady returned false\n");
        return 1;
    }
    const char *legacy[] = {
        "BNNSGraphCompileFromFile",
        "BNNSGraphExecute",
        "BNNSGraphOptionsCreateDefault",
        "BNNSGraphOptionsSetSingleThread",
        "BNNSGraphGetWorkspaceSize",
        "BNNSGraphGetSize",
        "BNNSGraphContextGetArgPosition",
        "BNNSGraphGetNumInputs",
        "BNNSGraphGetInputNames",
        "BNNSGraphGetNumOutputs",
        "BNNSGraphGetOutputNames",
        "BNNSGraphGetTensorDescriptor",
        "BNNSGraphOptionsSetPredefinedOptimizations",
        "BNNSGraphGetArgumentPosition",
    };
    for (size_t i = 0; i < sizeof(legacy) / sizeof(legacy[0]); ++i) {
        required(handle, legacy[i]);
    }

    options_create_fn make_options = (options_create_fn)required(handle, "BNNSGraphOptionsCreateDefault");
    options_single_fn set_single = (options_single_fn)required(handle, "BNNSGraphOptionsSetSingleThread");
    options_optim_fn set_optim = (options_optim_fn)required(handle, "BNNSGraphOptionsSetPredefinedOptimizations");
    compile_fn compile = (compile_fn)required(handle, "BNNSGraphCompileFromFile");
    get_size_fn get_size = (get_size_fn)required(handle, "BNNSGraphGetSize");
    count_fn input_count = (count_fn)required(handle, "BNNSGraphGetNumInputs");
    count_fn output_count = (count_fn)required(handle, "BNNSGraphGetNumOutputs");
    names_fn input_names = (names_fn)required(handle, "BNNSGraphGetInputNames");
    names_fn output_names = (names_fn)required(handle, "BNNSGraphGetOutputNames");
    workspace_fn workspace_size = (workspace_fn)required(handle, "BNNSGraphGetWorkspaceSize");

    void *options = make_options();
    if (!options) {
        fprintf(stderr, "options creation failed\n");
        return 1;
    }
    set_single(options, 1);
    set_optim(options, 0xfe6ee789u);
    void *graph = compile(10, argv[2], NULL, options);
    if (!graph) {
        fprintf(stderr, "legacy compile failed\n");
        return 1;
    }
    size_t graph_bytes = get_size(graph);
    size_t inputs = input_count(graph, NULL);
    size_t outputs = output_count(graph, NULL);
    size_t workspace = workspace_size(graph);
    if (graph_bytes == (size_t)-1 || inputs == (size_t)-1 || outputs == (size_t)-1 || workspace == (size_t)-1) {
        fprintf(stderr, "graph query failed\n");
        return 1;
    }
    const char **in_names = calloc(inputs ? inputs : 1, sizeof(char *));
    const char **out_names = calloc(outputs ? outputs : 1, sizeof(char *));
    if (!in_names || !out_names) {
        fprintf(stderr, "allocation failed\n");
        return 1;
    }
    if (input_names(graph, NULL, inputs, in_names) || output_names(graph, NULL, outputs, out_names)) {
        fprintf(stderr, "name query failed\n");
        return 1;
    }
    printf("ready graph_bytes=%zu inputs=%zu outputs=%zu workspace=%zu\n", graph_bytes, inputs, outputs, workspace);
    return 0;
}
