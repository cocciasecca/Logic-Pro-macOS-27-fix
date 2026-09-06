// Legacy ABI bridge for Logic 11.2.2 arm64, macOS 27 build 26A5425a.
// Behavioral reference: BNNS wrappers from macOS 26.6.2 (25G83).
// No Apple implementation is linked or redistributed.
#include <Accelerate/Accelerate.h>
#include <dlfcn.h>
#include <stdint.h>
#include <limits.h>
#include <string.h>
#include <stdlib.h>
#include <stdio.h>

static size_t options_size;
static void (*set_optimizations)(bnns_graph_compile_options_t, uint32_t);
static size_t (*workspace_size)(bnns_graph_t, const char *);
static int (*execute_graph)(bnns_graph_t, const char *, size_t, bnns_graph_argument_t *, size_t, void *);
static int (*tensor_descriptor)(bnns_graph_t, const char *, const char *, bool, void *);
static int ready;

__attribute__((constructor)) static void initialize(void) {
    void *a = dlopen("/System/Library/Frameworks/Accelerate.framework/Accelerate", RTLD_NOW|RTLD_LOCAL);
    if (!a) return;
    set_optimizations = dlsym(a, "BNNSGraphCompileOptionsSetPredefinedOptimizations");
    workspace_size = dlsym(a, "BNNSGraphGetWorkspaceSize_v2");
    execute_graph = dlsym(a, "BNNSGraphExecute_v2");
    tensor_descriptor = dlsym(a, "BNNSGraphGetTensorDescriptor_v2");
    bnns_graph_compile_options_t o = BNNSGraphCompileOptionsMakeDefault();
    options_size = o.size;
    if (o.data) BNNSGraphCompileOptionsDestroy(o);
    ready = options_size && set_optimizations && workspace_size && execute_graph && tensor_descriptor;
}
int BNNSCompatReady(void) { return ready; }

size_t LegacySize(void *p) __asm__("_BNNSGraphGetSize");
size_t LegacySize(void *p) {
    if (!p) return SIZE_MAX;
    uint32_t magic, version; size_t bytes;
    memcpy(&magic,p,4); memcpy(&version,(char *)p+4,4); memcpy(&bytes,(char *)p+8,8);
    // Same serialized header as reference. Current generated version is tested.
    if (magic != 0xd7dba027 || !version || version > 0x50000 || bytes < 16) return SIZE_MAX;
    return bytes;
}
static bnns_graph_t graph(void *p) { return (bnns_graph_t){p, LegacySize(p)}; }
static bnns_graph_compile_options_t options(void *p) {
    return (bnns_graph_compile_options_t){p, p ? options_size : 0};
}
void *LegacyOptions(void) __asm__("_BNNSGraphOptionsCreateDefault");
void *LegacyOptions(void) { return ready ? BNNSGraphCompileOptionsMakeDefault().data : NULL; }
void LegacySingle(void *p, bool single) __asm__("_BNNSGraphOptionsSetSingleThread");
void LegacySingle(void *p, bool single) { if (ready) BNNSGraphCompileOptionsSetTargetSingleThread(options(p),single); }
void LegacyOptimization(void *p, uint32_t mask) __asm__("_BNNSGraphOptionsSetPredefinedOptimizations");
void LegacyOptimization(void *p, uint32_t mask) { if (ready) set_optimizations(options(p),mask); }
void *LegacyCompile(uint32_t format,const char *file,const char *function,void *p) __asm__("_BNNSGraphCompileFromFile");
void *LegacyCompile(uint32_t format,const char *file,const char *function,void *p) {
    // Only the format used by the inspected Logic call sites is supported.
    if (!ready || format != 10 || !file) return NULL;
    bnns_graph_t g = BNNSGraphCompileFromFile(file,function,options(p));
    if (g.data && LegacySize(g.data) != g.size) { free(g.data); return NULL; }
    return g.data;
}
size_t LegacyInputs(void *p,const char *f) __asm__("_BNNSGraphGetNumInputs");
size_t LegacyInputs(void *p,const char *f) { return BNNSGraphGetInputCount(graph(p),f); }
size_t LegacyOutputs(void *p,const char *f) __asm__("_BNNSGraphGetNumOutputs");
size_t LegacyOutputs(void *p,const char *f) { return BNNSGraphGetOutputCount(graph(p),f); }
int LegacyInputNames(void *p,const char *f,size_t n,const char **names) __asm__("_BNNSGraphGetInputNames");
int LegacyInputNames(void *p,const char *f,size_t n,const char **names) { return BNNSGraphGetInputNames(graph(p),f,n,names); }
int LegacyOutputNames(void *p,const char *f,size_t n,const char **names) __asm__("_BNNSGraphGetOutputNames");
int LegacyOutputNames(void *p,const char *f,size_t n,const char **names) { return BNNSGraphGetOutputNames(graph(p),f,n,names); }
int LegacyTensor(void *p,const char *f,const char *name,bool fill,void *tensor) __asm__("_BNNSGraphGetTensorDescriptor");
int LegacyTensor(void *p,const char *f,const char *name,bool fill,void *tensor) {
    return ready ? tensor_descriptor(graph(p),f,name,fill,tensor) : -1;
}
size_t LegacyWorkspace(void *p) __asm__("_BNNSGraphGetWorkspaceSize");
size_t LegacyWorkspace(void *p) { return ready ? workspace_size(graph(p),NULL) : SIZE_MAX; }
int LegacyExecute(void *p,void **buffers,void *workspace) __asm__("_BNNSGraphExecute");
int LegacyExecute(void *p,void **buffers,void *workspace) {
    if (!ready) return -1;
    bnns_graph_t g=graph(p);
    size_t ni=BNNSGraphGetInputCount(g,NULL), no=BNNSGraphGetOutputCount(g,NULL);
    if (ni>1024 || no>1024 || ni+no>1024 || !buffers) return -1;
    size_t count=ni+no;
    bnns_graph_argument_t args[1024];
    for (size_t i=0;i<count;++i) args[i]=(bnns_graph_argument_t){.data_ptr=buffers[i],.data_ptr_size=SIZE_MAX};
    size_t bytes=workspace ? workspace_size(g,NULL) : 0;
    if (bytes==SIZE_MAX) return -1;
    return execute_graph(g,NULL,count,args,bytes,workspace);
}
// This obsolete context entry has no caller in the inspected Logic arm64 slice.
// Do not synthesize a context size or touch an unknown private context layout.
int LegacyContextPosition(void *p,const char *name) __asm__("_BNNSGraphContextGetArgPosition");
int LegacyContextPosition(void *p,const char *name) { (void)p; (void)name; return INT_MAX; }
