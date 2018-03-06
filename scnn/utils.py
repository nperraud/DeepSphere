import healpy as hp
import numpy as np
from scipy import sparse


def healpix_weightmatrix(nside=16, nest=True, indexes=None, dtype=np.float32):
    '''Return an unknormalized Weight matrix for a graph using the HEALPIX sampling

    Parameters
    ----------
    nside : int, scalar or array-like
            The healpix nside parameter, must be a power of 2, less than 2**30
    nest : nest : bool, optional
           if True, assume NESTED pixel ordering, otherwise, RING pixel ordering
    indexes: list of indexes to use. With None, all indexes are used. This 
           allows to build the graph only on a subpart of the sphere 
           (default None, all sphere)
    '''

    npix = nside**2 * 12  # number of pixels
    pix = range(npix)

    if indexes is None:
        indexes = pix

    # 1) get the coordinates
    [x, y, z] = hp.pix2vec(nside, pix, nest=nest)
    coords = np.vstack([x, y, z]).transpose()

    # 2) get the 8 neighboors
    [theta, phi] = hp.pix2ang(nside, indexes, nest=nest)
    nused = theta.shape[0]

    index_neighboor = hp.pixelfunc.get_all_neighbours(
        nside, theta=theta, phi=phi, nest=nest)

    # 3) build the adjacency matrix
    # The following code is equivalent to the following one
    # (it returns numpy array though)
    # row_index = []
    # col_index = []
    # for row in pix:
    #     for col in index_neighboor[:,row]:
    #         if col>=0:
    #             row_index.append(row)
    #             col_index.append(col)
    col_index = np.reshape(index_neighboor.T, [nused * 8])
    row_index = np.reshape(
        np.reshape(np.array(list(indexes) * 8), [8, nused]).T, [8 * nused])
    good_index = col_index >= 0
    col_index = col_index[good_index]
    row_index = row_index[good_index]

    dist = np.array(
        [
            sum((coords[row] - coords[col])**2)
            for row, col in zip(row_index, col_index)
        ],
        dtype=dtype)

    mean_dist = np.mean(dist)
    w = np.exp(-dist / (2 * mean_dist))
    W = sparse.csr_matrix(
        (w, (row_index, col_index)), shape=(npix, npix), dtype=dtype)

    W = W[indexes, :]
    W = W[:, indexes]

    return W


def build_laplacian(W, lap_type='normalized', dtype=np.float32):
    d = np.ravel(W.sum(1))
    if lap_type == 'combinatorial':
        D = sparse.diags(d, 0, dtype=dtype)
        return (D - W).tocsc()
    elif lap_type == 'normalized':
        d12 = np.power(d, -0.5)
        D12 = sparse.diags(np.ravel(d12), 0, dtype=dtype).tocsc()
        return sparse.identity(d.shape[0], dtype=dtype) - D12 * W * D12
    else:
        raise ValueError('Unknown Laplacian type {}'.format(lap_type))


# build a healpix graph using the pygsp from NSIDE
def healpix_graph(nside=16,
                  nest=True,
                  lap_type='normalized',
                  indexes=None,
                  dtype=np.float32):
    from pygsp import graphs
    # 1) get the coordinates
    npix = nside**2 * 12  # number of pixels
    pix = range(npix)
    [x, y, z] = hp.pix2vec(nside, pix, nest=nest)
    coords = np.vstack([x, y, z]).transpose()
    # 2) computing the weight matrix
    W = healpix_weightmatrix(
        nside=nside, nest=nest, indexes=indexes, dtype=dtype)
    # 3) building the graph
    G = graphs.Graph(
        W, gtype='healpix', lap_type=lap_type, coords=coords)
    return G


def healpix_laplacian(nside=16,
                      nest=True,
                      lap_type='normalized',
                      indexes=None,
                      dtype=np.float32):
    W = healpix_weightmatrix(
        nside=nside, nest=nest, indexes=indexes, dtype=dtype)
    L = build_laplacian(W, lap_type=lap_type)
    return L


def rescale_L(L, lmax=2):
    """Rescale the Laplacian eigenvalues in [-1,1]."""
    M, M = L.shape
    I = sparse.identity(M, format='csr', dtype=L.dtype)
    L /= lmax / 2
    L -= I
    return L


def build_laplacians(nsides, indexes=None):
    L = []
    p = []
    first = True
    if indexes is None:
        indexes = [None] * len(nsides)
    for nside, ind in zip(nsides, indexes):
        if not first:
            pval = (nside_old // nside)**2
            p.append(pval)
        nside_old = nside
        first = False
        Lt = healpix_laplacian(nside=nside, indexes=ind)
        L.append(Lt)
    if len(L):
        p.append(1)
    return L, p