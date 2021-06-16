import torch
from torch_geometric.nn import SAGEConv
import collections
import torch.nn.functional as F
from torch import nn
from typing import Iterable
from torch.distributions import Normal,Poisson
from torch.distributions import Normal, kl_divergence as kl
import pytorch_lightning as pl

def reparameterize_gaussian(mu, var):
    return Normal(mu, var.sqrt()).rsample()

class SAGE(pl.LightningModule):
    """
    GraphSAGE based model in combination with scvi variational autoencoder.

    SAGE will learn to encode neighbors to allow either the reconstruction of the original nodes data helped by neighbor data or 
    to generate similar embedding for closeby nodes (i.e. regionalization).

 
    """ 

    def __init__(self, 
        in_channels :int, 
        hidden_channels:int,
        num_layers:int=2,
        normalize:bool=True,
        apply_normal_latent:bool=False,
        supervised_decoder:bool=False,
        output_channels:int=448,
        supervised_loss:str= 'matmul', # choose 
        ):


        super().__init__()
        self.save_hyperparameters()

        self.num_layers = num_layers
        self.normalize = normalize
        self.convs = torch.nn.ModuleList()
        self.apply_normal_latent = apply_normal_latent
        self.supervised_decoder = supervised_decoder
        self.supervised_loss = supervised_loss

        for i in range(num_layers):
            in_channels = in_channels if i == 0 else hidden_channels
            # L2 regularization only on last layer
            if i == num_layers-1:
                self.convs.append(SAGEConv(in_channels, hidden_channels,normalize=self.normalize))
            else:
                self.convs.append(SAGEConv(in_channels, hidden_channels,normalize=False))

        if self.apply_normal_latent:
            self.mean_encoder = nn.Linear(hidden_channels, hidden_channels)
            self.var_encoder = nn.Linear(hidden_channels, hidden_channels)

        if self.supervised_decoder:
            if self.supervised_loss != 'kl-poisson':
                self.decoder = DecoderSCVI(hidden_channels,output_channels,softmax=False)   
            else:
                self.decoder = DecoderSCVI(hidden_channels,output_channels,softmax=False)
                
        
    def neighborhood_forward(self,x,adjs):
        x = torch.log(x + 1)
        for i, (edge_index, _, size) in enumerate(adjs):
            x_target = x[:size[1]]  # Target nodes are always placed first.

            x = self.convs[i]((x, x_target), edge_index)
            if i != self.num_layers - 1:
                x = x.relu()
                x = F.dropout(x, p=0.1, training=self.training)

        if self.apply_normal_latent:
            q_m = self.mean_encoder(x)
            q_v = torch.exp(self.var_encoder(x)) + 1e-4
            x = reparameterize_gaussian(q_m, q_v)
        else:
            q_m = 0
            q_v = 0

        return x, q_m, q_v

    def forward(self,x,pos_x,neg_x,adjs,ref):
        # Embedding sampled nodes
        z, q_m, q_v = self.neighborhood_forward(x,adjs)
        # Embedding for neighbor nodes of sample nodes
        z_pos, q_m_pos, q_v_pos = self.neighborhood_forward(pos_x,adjs)
        # Ebedding for random nodes
        z_neg, q_m_pos, q_v_pos = self.neighborhood_forward(neg_x,adjs)

        pos_loss = F.logsigmoid((z * z_pos).sum(-1))
        neg_loss = F.logsigmoid(-(z * z_neg).sum(-1))
        #ratio = pos_loss/neg_loss + 1e-8

        pos_loss = pos_loss.mean()
        neg_loss = neg_loss.mean()
        n_loss = - pos_loss - neg_loss

        # KL Divergence
        if self.apply_normal_latent:
            mean = torch.zeros_like(q_m)
            scale = torch.ones_like(q_v)
            kl_divergence_z = kl(Normal(q_m, torch.sqrt(q_v)), Normal(mean, scale)).sum(dim=1)
            n_loss = n_loss + kl_divergence_z.mean()
        
        # Add loss if trying to reconstruct cell types
        if self.supervised_decoder:
            px =  self.decoder(z)
            if self.supervised_loss == 'kl-poisson':
                supervised_loss = 0
                #supervised_loss = kl(Poisson(px),Poisson(torch.log(ref+1))).sum(dim=1).mean()
            elif self.supervised_loss == 'cosine-similarity':
                cos= 0
                for c in range(px.shape[0]):
                    cos += -torch.nn.functional.cosine_similarity(px[c:c+1,:],ref.T).max()
                cos = cos/px.shape[0]
                supervised_loss = cos
            elif self.supervised_loss == 'matmul':
                supervised_loss = - F.log_softmax(torch.matmul(px,ref),dim=1).sum(dim=-1).mean()/1000

            n_loss += supervised_loss
            #print(supervised_loss)
            self.log('Autoencoder Loss',supervised_loss)
            
        return n_loss

    def configure_optimizers(self):
        optimizer = torch.optim.Adam(self.parameters(), lr=0.001)
        return optimizer

    def training_step(self, batch, batch_idx):
        x,pos,neg,adjs,c = batch
        loss= self(x,pos,neg,adjs,c)
        self.log('train_loss', loss)
        return loss

    def validation_step(self, batch, batch_idx):
        x,pos,neg,adjs,c = batch
        loss= self(x,pos,neg,adjs,c)
        self.log('val_loss', loss)
        return loss
    
# Decoder
class DecoderSCVI(nn.Module):
    def __init__(
        self,
        n_input: int,
        n_output: int,
        n_hidden: int = 48,
        use_batch_norm: bool=True,
        use_relu:bool=True,
        dropout_rate: float=0.1,
        bias: bool=True,
        softmax:bool = True,
    ):
        super().__init__()

        self.px_decoder = nn.Sequential(
                            nn.Linear(n_input , n_hidden, bias=bias),
                            nn.BatchNorm1d(n_hidden, momentum=0.01, eps=0.001) if use_batch_norm else None,
                            nn.ReLU() if use_relu else None,
                            nn.Dropout(p=dropout_rate) if dropout_rate > 0 else None)

        if softmax:
            self.px_scale_decoder = nn.Sequential(nn.Linear(n_hidden, n_output))
        else:
            self.px_scale_decoder = nn.Sequential(nn.Linear(n_hidden, n_output),
                nn.Softmax(dim=-1))

    def forward(
        self, z: torch.Tensor
    ):
        # The decoder returns values for the parameters of the ZINB distribution
        px = self.px_decoder(z)
        px= self.px_scale_decoder(px)
        return px
