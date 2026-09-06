// Public-API inference probe. Does not load or launch Logic or emit audio.
#include <Accelerate/Accelerate.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <math.h>

int main(int argc, char **argv) {
    if (argc != 2) { fprintf(stderr, "Usage: modern_bnns_probe model.mil\n"); return 2; }
    int result = 4;
    size_t count = 0, total = 0;
    const size_t budget = 512 * 1024 * 1024;
    const char **names = NULL;
    BNNSTensor *tensors = NULL;
    bnns_graph_argument_t *args = NULL;
    void *workspace = NULL;
    bnns_graph_context_t context = {0};
    bnns_graph_compile_options_t options = BNNSGraphCompileOptionsMakeDefault();
    if (!options.data) return 3;
    BNNSGraphCompileOptionsSetTargetSingleThread(options, true);
    bnns_graph_t graph = BNNSGraphCompileFromFile(argv[1], NULL, options);
    BNNSGraphCompileOptionsDestroy(options);
    if (!graph.data || !graph.size) {
        fprintf(stderr, "Public BNNS compilation failed.\n");
        goto cleanup;
    }
    count = BNNSGraphGetArgumentCount(graph, NULL);
    if (count == 0 || count > 4096) goto cleanup;
    printf("graph_bytes=%zu inputs=%zu outputs=%zu arguments=%zu\n", graph.size,
           BNNSGraphGetInputCount(graph, NULL), BNNSGraphGetOutputCount(graph, NULL), count);
    names = calloc(count, sizeof(*names));
    tensors = calloc(count, sizeof(*tensors));
    args = calloc(count, sizeof(*args));
    if (!names || !tensors || !args) goto cleanup;
    if (BNNSGraphGetArgumentNames(graph, NULL, count, names)) goto cleanup;
    context = BNNSGraphContextMake(graph);
    if (!context.data) goto cleanup;
    if (BNNSGraphContextSetArgumentType(context, BNNSGraphArgumentTypeTensor)) goto cleanup;
    for (size_t i = 0; i < count; ++i) {
        if (BNNSGraphContextGetTensor(context, NULL, names[i], true, &tensors[i])) goto cleanup;
        size_t bytes = BNNSTensorGetAllocationSize(&tensors[i]);
        if (!bytes || bytes > budget - total) goto cleanup;
        total += bytes;
        if (posix_memalign(&tensors[i].data, 64, bytes)) goto cleanup;
        memset(tensors[i].data, 0, bytes);
        tensors[i].data_size_in_bytes = bytes;
        args[i].tensor = &tensors[i];
    }
    size_t bytes = BNNSGraphContextGetWorkspaceSize(context, NULL);
    if (bytes > budget - total) goto cleanup;
    if (bytes && posix_memalign(&workspace, 64, bytes)) goto cleanup;
    // Repeat to check basic context reuse; numerical/audio equivalence is NOT tested.
    for (int iteration = 0; iteration < 3; ++iteration)
        if (BNNSGraphContextExecute(context, NULL, count, args, bytes, workspace)) goto cleanup;
    for (size_t i = 0; i < count; ++i) {
        if (tensors[i].data_type != BNNSDataTypeFloat32) continue;
        const float *values = tensors[i].data;
        for (size_t j = 0; j < tensors[i].data_size_in_bytes / sizeof(float); ++j)
            if (!isfinite(values[j])) goto cleanup;
    }
    printf("three_zero_input_executions=passed finite_float32_buffers=passed workspace_bytes=%zu\n", bytes);
    result = 0;
cleanup:
    if (context.data) BNNSGraphContextDestroy(context);
    if (tensors) for (size_t i = 0; i < count; ++i) free(tensors[i].data);
    free(workspace); free(args); free(tensors); free(names); free(graph.data);
    if (result) fprintf(stderr, "Probe failed (compilation, query, allocation, execution, or finite-value check).\n");
    return result;
}
