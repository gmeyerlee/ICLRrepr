"""
Implements graph based hierarchical convolutional network encoding, as found in the anonymous
paper submitted to ICLR 2018
"""

import keras
import random
import numpy as np

class Motif(object):
    def __init__(self, num_nodes, prev_motifs=[], level=2, G=None):
        if level < 0:
            raise ValueError('Invalid level value')
        self.__size = num_nodes
        self.__level = level
        # if lowest non primitive level operations are primitive
        if level == 2:
            self.__o = [ None,'no_op', 'ident','1x1','3x3_depth','3x3_sep', 'max_pool', 'avg_pool']
        # otherwise build operations from previous level of motifs
        else:
            self.__o = [ None, 'no_op', 'ident' ]
            self.__o.extend(prev_motifs)
        # initialize adjacency matrix to encode linear chain of identity connections
        ones = np.ones((num_nodes, num_nodes), dtype=int)
        if G is not None:
            self.__G = G
        else:
            self.__G = np.tril(ones, -1)
            for j in range(1,num_nodes):
                self.__G.itemset((j,j-1), 2)

    level = property(lambda self: self.__level)

    def decode(self, inputs, c):
        x_tens = []
        x_tens.append(inputs)
        if self.__level > 2:
            for i in range(1, self.__size):
                new_x = []
                for j in range(i):
                    op = self.__o[self.__G.item((i,j))]
                    if op is None:
                        raise IndexError('Attempt to access invalid graph edge')
                    elif op == 'no_op':
                        continue
                    elif op == 'ident':
                        new_x.append(x_tens[j])
                    else:
                        new_x.append(op.decode(x_tens[j], c))
                if len(new_x) == 0:
                    self.__G.itemset((i,i-1), 2)
                    x_tens.append(x_tens[i-1])
                elif len(new_x) == 1:
                    x_tens.append(new_x[0])
                else:
                    x2 = keras.layers.Concatenate()(new_x)
                    x_tens.append(keras.layers.Conv2D(c, 1, padding='same', activation='relu')(x2))
        elif self.__level == 2:
            for i in range(1, self.__size):
                new_x = []
                for j in range(i):
                    op = self.__o[self.__G.item((i,j))]
                    if op is None or op == 'no_op':
                        continue
                    elif op == 'ident':
                        new_x.append(x_tens[j])
                    elif op == '1x1':
                        x_temp = keras.layers.Conv2D(c, 1, padding='same', activation='relu')(x_tens[j])
                        new_x.append(keras.layers.BatchNormalization()(x_temp))
                    elif op == '3x3_depth':
                        x_temp = keras.layers.Conv2D(c, 3, padding='same', activation='relu')(x_tens[j])
                        new_x.append(keras.layers.BatchNormalization()(x_temp))
                    elif op == '3x3_sep':
                        x_temp = keras.layers.SeparableConv2D(c, 3, padding='same', activation='relu')(x_tens[j])
                        new_x.append(keras.layers.BatchNormalization()(x_temp))
                    elif op == 'max_pool':
                        new_x.append(keras.layers.MaxPooling2D(3, strides=1, padding='same')(x_tens[j]))
                    elif op == 'avg_pool':
                        new_x.append(keras.layers.AveragePooling2D(3, strides=1, padding='same')(x_tens[j]))
                    else:
                        raise ValueError('Invalid level 1 motif: '+op)
                if len(new_x) == 0:
                    self.__G.itemset((i,i-1), 2)
                    x_tens.append(x_tens[i-1])
                elif len(new_x) == 1:
                    x_tens.append(new_x[0])
                else:
                    x_tens.append(keras.layers.Concatenate()(new_x))
        assert len(x_tens) == self.__size, 'Size Error: ' + str(len(x_tens)) + ' ' + str(self.__size)
        return x_tens[-1]

    def mutate(self):
        i = random.randrange(1, self.__size)
        j = random.randrange(i)
        self.__G.itemset((i,j), random.randrange(1,len(self.__o)))

    def copy(self):
        return Motif(self.__size, self.__o[3:], self.__level, self.__G)

class Architecture(object):
    def __init__(self, num_nodes):
        self._num_nodes = num_nodes
        self.fitness = 0

    def __cmp__(self, other):
        return cmp(self.fitness, other.fitness)

    def __lt__(self, other):
        return self.fitness < other.fitness

    def __gt__(self, other):
        return self.fitness > other.fitness

    def mutate(self):
        raise NotImplementedError

    def assemble(self, inputs):
        raise NotImplementedError

class FlatArch(Architecture):
    def __init__(self, num_nodes, motifs=None):
        super(FlatArch, self).__init__(num_nodes)
        if motifs is not None:
            self.__m = motifs
        else:
            self.__m = Motif(num_nodes)

    def mutate(self):
        self.__m.mutate()

    def assemble(self, inputs, c):
        output = self.__m.decode(inputs, c)
        return output

    def copy(self):
        return FlatArch(self._num_nodes, motifs=self.__m.copy())

class HierArch(Architecture):
    def __init__(self, num_nodes, num_levels, num_motifs, motifs=None):
        super(HierArch, self).__init__(num_nodes)
        assert num_levels > 2, "Insufficent levels to require hierarchical architecture"
        self.height = num_levels
        self._num_motifs = num_motifs
        self.__m = []
        if motifs is not None:
            self.__m = motifs
        else:
            for i in range(0, num_levels-1):
                self.__m.insert(i,[])
                for j in range(num_motifs[i]):
                    if i == 0:
                        self.__m[i].append(Motif(num_nodes[i]))
                    else:
                        self.__m[i].append(Motif(num_nodes[i], prev_motifs = self.__m[i-1], level=i+2))

    def mutate(self):
        l = random.randint(2, self.height)
        m_ind = random.randrange(self._num_motifs[l-2])
        m = self.__m[l-2][m_ind]
        m.mutate()

    def assemble(self, inputs, c):
        output = self.__m[self.height-2][0].decode(inputs, c)
        return output

    def copy(self):
        new_m = []
        for motif in self.__m:
            new_m.append(motif.copy())
        return HierArch(self._num_nodes, self.height, self._num_motifs, motifs=new_m)
