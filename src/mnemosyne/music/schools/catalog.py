"""Verify published artifacts and write the listening index (no audio rendering)."""
import argparse
import hashlib
import json
from pathlib import Path
from . import SCHOOLS

LISTEN = {
    'tintinnabuli': 'Ступенное движение мелодии и ближайшие звуки трезвучия.',
    'stochastic': 'Неравномерные появления звуков и движущиеся струнные массы.',
    'micropolyphony': 'Один хроматический рисунок растворяется в тесных канонах.',
    'serial': 'Полные двенадцатитоновые ряды распределяются между тембрами.',
    'feldman': 'Тихие неравные циклы; при возвращении меняется одна длительность или высота.',
    'process': 'Одинаковые пульсирующие фигуры расходятся по фазе; затем наращивание и замещение.',
    'additive': 'Ячейки удлиняются и сокращаются на фоне медленных гармонических смен.',
    'in_c': 'Новые общие модули, независимые повторения и ограниченная дистанция между игроками.',
    'spectral': 'Распределённые обертоны постепенно растягиваются в негармонический спектр; четвертитоны.',
    'sonorism': 'Четвертитоновые полосы и поля глиссандо; синтетические приближения струнных техник.',
    'messiaen': 'Симметричный лад, палиндромные ритмы с добавленной длительностью, птичьи арабески и аккорды.',
    'ustvolskaya': 'Молотковые кластеры сменяются тихими унисонами; крайние динамические контрасты.',
    'chance': 'Независимые броски монет выбирают звук, длительность, динамику и молчание; синтетическая подготовка рояля.',
    'tempo_canon': 'Одна фигура в ускоряющихся канонах с отношениями √2, √3 и золотым сечением; временная сетка 1/32 четверти.',
    'aleatoric_counterpoint': 'Согласованные рамки окружают несинхронные повторы; записана одна реализация ad libitum.',
    'fibonacci': 'Пропорции формы 2:3:5:8:13; ритмы Фибоначчи/Люка противопоставляют диатонику хроматике.',
    'polystylism': 'Архивный ноктюрн NotaGen сталкивается с хроматическими вторжениями.',
    'scelsi': 'Один высотный центр с четвертитоновыми отклонениями; форма в динамике и синтетическом тембре.',
    'drone': 'Постепенный вход чисто настроенных обертонов; точные отношения в аудио, округление с указанием центов в нотах.',
    'gregorian': 'Одноголосный хорал в церковном ладу: речитация на тоне, невмы и мелизмы, кантор и хор над исоном.',
    'ancient_greek': 'Строки из долгих и кратких слогов в диатонике, хроматике и энармонике с четвертитонами; лира и авлос вторят голосу.',
}


def write_index(root):
    lines = ['# Schools — listening index', '',
             'Методические этюды; художественная оценка остаётся за слушателем. Аудио включает 2 секунды хвоста.', '',]
    for school in SCHOOLS:
        folder = root/school
        manifest = json.loads((folder/'render.json').read_text())
        for name, digest in manifest['artifacts'].items():
            if hashlib.sha256((folder/name).read_bytes()).hexdigest() != digest:
                raise ValueError(f'Changed or incomplete artifact: {folder/name}')
        plan = json.loads((folder/'plan.json').read_text())
        lines.append(f"- [{school}]({school}/score.mp3) · [PDF]({school}/score.pdf) · {plan['duration']} с · {plan['ensemble']} — {LISTEN[school]}")
    (root/'INDEX.md').write_text('\n'.join(lines)+'\n')
    print(f'Verified {len(SCHOOLS)} schools; wrote {root}/INDEX.md')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    write_index(parser.parse_args().root)
