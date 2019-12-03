#AUTOGENERATED! DO NOT EDIT! File to edit: dev/37_text.learner.ipynb (unless otherwise specified).

__all__ = ['match_embeds', 'RNNLearner', 'language_model_learner', 'text_classifier_learner']

#Cell
from ..basics import *
from .core import *
from .data import *
from .models.core import *
from .models.awdlstm import *
from ..callback.rnn import *

#Cell
def match_embeds(old_wgts, old_vocab, new_vocab):
    "Convert the embedding in `wgts` to go with a new vocabulary."
    bias, wgts = old_wgts.get('1.decoder.bias', None), old_wgts['0.encoder.weight']
    wgts_m = wgts.mean(0)
    new_wgts = wgts.new_zeros((len(new_vocab),wgts.size(1)))
    if bias is not None:
        bias_m = bias.mean(0)
        new_bias = bias.new_zeros((len(new_vocab),))
    old_o2i = old_vocab.o2i if hasattr(old_vocab, 'o2i') else {w:i for i,w in enumerate(old_vocab)}
    for i,w in enumerate(new_vocab):
        idx = old_o2i.get(w, -1)
        new_wgts[i] = wgts[idx] if idx>=0 else wgts_m
        if bias is not None: new_bias[i] = bias[idx] if idx>=0 else bias_m
    old_wgts['0.encoder.weight'] = new_wgts
    if '0.encoder_dp.emb.weight' in old_wgts: old_wgts['0.encoder_dp.emb.weight'] = new_wgts.clone()
    old_wgts['1.decoder.weight'] = new_wgts.clone()
    if bias is not None: old_wgts['1.decoder.bias'] = new_bias
    return old_wgts

#Cell
@delegates(Learner.__init__)
class RNNLearner(Learner):
    "Basic class for a `Learner` in NLP."
    def __init__(self, model, dbunch, loss_func, alpha=2., beta=1., **kwargs):
        super().__init__(model, dbunch, loss_func, **kwargs)
        self.add_cb(RNNTrainer(alpha=alpha, beta=beta))

    def save_encoder(self, file):
        "Save the encoder to `self.path/self.model_dir/file`"
        if rank_distrib(): return # don't save if slave proc
        encoder = get_model(self.model)[0]
        if hasattr(encoder, 'module'): encoder = encoder.module
        torch.save(encoder.state_dict(), join_path_file(file,self.path/self.model_dir, ext='.pth'))

    def load_encoder(self, file, device=None):
        "Load the encoder `name` from the model directory."
        encoder = get_model(self.model)[0]
        if device is None: device = self.dbunch.device
        if hasattr(encoder, 'module'): encoder = encoder.module
        distrib_barrier()
        encoder.load_state_dict(torch.load(join_path_file(file,self.path/self.model_dir, ext='.pth'), map_location=device))
        self.freeze()
        return self

    #TODO: When access is easier, grab new_vocab from self.dbunch
    def load_pretrained(self, wgts_fname, vocab_fname, new_vocab, strict=True):
        "Load a pretrained model and adapt it to the data vocabulary."
        old_vocab = Path(vocab_fname).load()
        wgts = torch.load(wgts_fname, map_location = lambda storage,loc: storage)
        if 'model' in wgts: wgts = wgts['model'] #Just in case the pretrained model was saved with an optimizer
        wgts = match_embeds(wgts, old_vocab, new_vocab)
        self.model.load_state_dict(wgts, strict=strict)
        self.freeze()
        return self

#Cell
from .models.core import _model_meta

#Cell
#TODO: When access is easier, grab vocab from dbunch
@delegates(Learner.__init__)
def language_model_learner(dbunch, arch, vocab, config=None, drop_mult=1., pretrained=True, pretrained_fnames=None, **kwargs):
    "Create a `Learner` with a language model from `data` and `arch`."
    model = get_language_model(arch, len(vocab), config=config, drop_mult=drop_mult)
    meta = _model_meta[arch]
    learn = RNNLearner(dbunch, model, loss_func=CrossEntropyLossFlat(), splitter=meta['split_lm'], **kwargs)
    #TODO: add backard
    #url = 'url_bwd' if data.backwards else 'url'
    if pretrained or pretrained_fnames:
        if pretrained_fnames is not None:
            fnames = [learn.path/learn.model_dir/f'{fn}.{ext}' for fn,ext in zip(pretrained_fnames, ['pth', 'pkl'])]
        else:
            if 'url' not in meta:
                warn("There are no pretrained weights for that architecture yet!")
                return learn
            model_path = untar_data(meta['url'] , c_key='model')
            fnames = [list(model_path.glob(f'*.{ext}'))[0] for ext in ['pth', 'pkl']]
        learn = learn.load_pretrained(*fnames, vocab)
    return learn

#Cell
#TODO: When access is easier, grab vocab from dbunch
@delegates(Learner.__init__)
def text_classifier_learner(dbunch, arch, vocab, bptt=72, config=None, pretrained=True, drop_mult=1.,
                            lin_ftrs=None, ps=None, **kwargs):
    "Create a `Learner` with a text classifier from `data` and `arch`."
    model = get_text_classifier(arch, len(vocab), get_c(dbunch), bptt=bptt, config=config,
                                drop_mult=drop_mult, lin_ftrs=lin_ftrs, ps=ps)
    meta = _model_meta[arch]
    learn = RNNLearner(dbunch, model, loss_func=CrossEntropyLossFlat(), splitter=meta['split_clas'], **kwargs)
    if pretrained:
        if 'url' not in meta:
            warn("There are no pretrained weights for that architecture yet!")
            return learn
        model_path = untar_data(meta['url'], c_key='model')
        fnames = [list(model_path.glob(f'*.{ext}'))[0] for ext in ['pth', 'pkl']]
        learn = learn.load_pretrained(*fnames, vocab, strict=False)
        learn.freeze()
    return learn

#Cell
@typedispatch
def show_results(x: LMTensorText, y, samples, outs, ctxs=None, max_n=10, **kwargs):
    if ctxs is None: ctxs = get_empty_df(min(len(samples), max_n))
    for i,l in enumerate(['input', 'target']):
        ctxs = [b.show(ctx=c, label=l, **kwargs) for b,c,_ in zip(samples.itemgot(i),ctxs,range(max_n))]
    ctxs = [b.show(ctx=c, label='pred', **kwargs) for b,c,_ in zip(outs.itemgot(0),ctxs,range(max_n))]
    display_df(pd.DataFrame(ctxs))
    return ctxs

#Cell
@typedispatch
def show_results(x: TensorText, y, samples, outs, ctxs=None, max_n=10, **kwargs):
    if ctxs is None: ctxs = get_empty_df(min(len(samples), max_n))
    ctxs = show_results[object](x, y, samples, outs, ctxs=ctxs, max_n=max_n, **kwargs)
    display_df(pd.DataFrame(ctxs))
    return ctxs

#Cell
@typedispatch
def plot_top_losses(x: TensorText, y:TensorCategory, samples, outs, raws, losses, **kwargs):
    rows = get_empty_df(len(samples))
    for i,l in enumerate(['input', 'target']):
        rows = [b.show(ctx=c, label=l, **kwargs) for b,c in zip(samples.itemgot(i),rows)]
    outs = L(o + (Float(r.max().item()), Float(l.item())) for o,r,l in zip(outs, raws, losses))
    for i,l in enumerate(['predicted', 'probability', 'loss']):
        rows = [b.show(ctx=c, label=l, **kwargs) for b,c in zip(outs.itemgot(i),rows)]
    display_df(pd.DataFrame(rows))