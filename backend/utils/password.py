import random


def gen_password(vk_id):
    return ''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz', k=5)) + str(vk_id)[:3]
