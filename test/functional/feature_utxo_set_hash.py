#!/usr/bin/env python3
# Copyright (c) 2020-2021 The Bitcoin Core developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.
"""Test UTXO set hash value calculation in gettxoutsetinfo."""

import struct

from test_framework.messages import (
    CBlock,
    COutPoint,
    FromHex,
)
from test_framework.muhash import MuHash3072
from test_framework.test_framework import BitcoinTestFramework
from test_framework.util import assert_equal
from test_framework.wallet import MiniWallet

class UTXOSetHashTest(BitcoinTestFramework):
    def set_test_params(self):
        self.num_nodes = 1
        self.setup_clean_chain = True

    def test_muhash_implementation(self):
        self.log.info("Test MuHash implementation consistency")

        node = self.nodes[0]
        wallet = MiniWallet(node)
        mocktime = node.getblockheader(node.getblockhash(0))['time'] + 1
        node.setmocktime(mocktime)

        # Generate 100 blocks and remove the first since we plan to spend its
        # coinbase
        block_hashes = wallet.generate(1) + node.generate(99)
        blocks = list(map(lambda block: FromHex(CBlock(), node.getblock(block, False)), block_hashes))
        blocks.pop(0)

        # Create a spending transaction and mine a block which includes it
        txid = wallet.send_self_transfer(from_node=node)['txid']
        tx_block = node.generateblock(output=wallet.get_address(), transactions=[txid])
        blocks.append(FromHex(CBlock(), node.getblock(tx_block['hash'], False)))

        # Unlike upstream, Xaya allows spending the genesis block's coinbase,
        # so we have to include that into the UTXO set.
        genesis = FromHex(CBlock(), node.getblock(node.getblockhash(0), False))
        blocks = [genesis] + blocks

        # Serialize the outputs that should be in the UTXO set and add them to
        # a MuHash object
        muhash = MuHash3072()

        for height, block in enumerate(blocks):
            # We spent the first mined block (after the genesis block).
            if height > 0:
                height += 1

            for tx in block.vtx:
                for n, tx_out in enumerate(tx.vout):
                    coinbase = 1 if not tx.vin[0].prevout.hash else 0

                    # Skip witness commitment
                    if (coinbase and n > 0):
                        continue

                    data = COutPoint(int(tx.rehash(), 16), n).serialize()
                    data += struct.pack("<i", height * 2 + coinbase)
                    data += tx_out.serialize()

                    muhash.insert(data)

        finalized = muhash.digest()
        node_muhash = node.gettxoutsetinfo("muhash")['muhash']

        assert_equal(finalized[::-1].hex(), node_muhash)

        # The values differ from upstream since in Xaya the genesis block's coinbase
        # is part of the UTXO set.
        self.log.info("Test deterministic UTXO set hash results")
        assert_equal(node.gettxoutsetinfo()['hash_serialized_2'], "450cb0874edb935d7243d3e83ea2dfe463729a7f08bbe701ab830f3927ce88da")
        assert_equal(node.gettxoutsetinfo("muhash")['muhash'], "5de773dfb84089156402f41bbfddf27652a3cf136e2bed2986a7ce6bc6db4a80")

    def run_test(self):
        self.test_muhash_implementation()


if __name__ == '__main__':
    UTXOSetHashTest().main()
