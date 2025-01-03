from .wallet import CryptoWallet
import time


def transfers() -> None:
    send_amount = 0.001
    
    w1 = CryptoWallet('sepolia')
    w2 = CryptoWallet('sepolia')

    print('w1 >> (Balance={}, Address={})'.format(
        w1.get_balance(), 
        w1.address
    ))
    
    while True:
        balance = w1.get_balance()
        
        if balance:
            if balance > send_amount:
                break
            
        time.sleep(10)
        
    print('Transaction Receipt: {}'.format(w1.send_transaction(w2.address, send_amount)))

    
if __name__ == "__main__":
    pass
