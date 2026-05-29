import h5py
import numpy as np
from pathlib import Path
from typing import Union

class HDF5GraphWriter:
    """
    Une classe pour gérer l'écriture séquentielle de graphes d'événements
    dans un unique fichier HDF5 avec une structure hiérarchique.

    Chaque événement est stocké comme un groupe HDF5 (ex: 'event_0', 'event_1', ...),
    contenant des datasets pour les features, les arêtes et les positions.

    Utilisation typique :
    with HDF5GraphWriter("output.h5") as writer:
        for i in range(num_events):
            # ... calculer x, edge_index, pos
            writer.write_event(event_idx=i, x=x, edge_index=edge_index, pos=pos)
    """

    def __init__(self, output_path: Union[str, Path], compression: str = 'gzip'):
        """
        Initialise le writer.

        Args:
            output_path (Union[str, Path]): Chemin vers le fichier HDF5 de sortie.
                                            Le fichier sera écrasé s'il existe.
            compression (str, optional): Algorithme de compression à utiliser.
                                         'gzip' est un bon compromis. 'lzf' est plus
                                         rapide mais compresse moins. None pour désactiver.
        """
        self.output_path = Path(output_path)
        self.compression = compression
        self.h5_file = None

    def __enter__(self):
        """
        Ouvre le fichier HDF5 en mode écriture lorsque le contexte `with` est entré.
        Ceci permet l'utilisation de `with HDF5GraphWriter(...) as writer:`.
        """
        # 'w' signifie write, ce qui écrasera le fichier s'il existe déjà.
        self.h5_file = h5py.File(self.output_path, 'w')
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        Ferme le fichier HDF5 lorsque le contexte `with` est quitté.
        Cette méthode est appelée automatiquement.
        """
        if self.h5_file:
            self.h5_file.close()

    def write_event(self, event_idx: int, **kwargs):
        """
        Écrit les données d'un unique événement dans le fichier HDF5.

        Crée un groupe pour l'événement et y sauvegarde chaque tableau NumPy
        fourni en tant que dataset HDF5.

        Args:
            event_idx (int): L'index de l'événement. Sera utilisé pour nommer le groupe.
            **kwargs: Paires clé-valeur où la clé est le nom du dataset (ex: 'x', 'edge_index')
                      et la valeur est le tableau NumPy à sauvegarder.
        """
        if not self.h5_file:
            raise IOError("Le fichier HDF5 n'est pas ouvert. "
                          "Utilisez cette classe dans un bloc 'with'.")

        # 1. Créer un groupe pour cet événement
        # Le nom du groupe sera par exemple "event_123"
        group_name = f"event_{event_idx}"
        event_group = self.h5_file.create_group(group_name)

        # 2. Itérer sur tous les tableaux fournis
        for name, data_array in kwargs.items():

            # print(f"Instance of {name} : {type(data_array)}")
            # print(f"Shape of {name} : {data_array.shape}")

            # 3. Créer un dataset HDF5 dans le groupe de l'événement
            # Check if it's a scalar (0-dimensional array) - don't use compression for scalars
            data_array = np.squeeze(data_array)
            if data_array.ndim == 0:
                event_group.create_dataset(
                    name=name,
                    data=data_array
                )
            else:
                event_group.create_dataset(
                    name=name,
                    data=data_array,
                    compression=self.compression
                )

    def add_metadata(self, **kwargs):
        """
        Ajoute des métadonnées globales au fichier HDF5.
        Les métadonnées sont stockées en tant qu'attributs de l'objet racine du fichier.

        Args:
            **kwargs: Paires clé-valeur pour les métadonnées à sauvegarder
                      (ex: source_file="/path/to/data.root", method="knn").
        """
        if not self.h5_file:
            raise IOError("Le fichier HDF5 n'est pas ouvert.")

        for key, value in kwargs.items():
            self.h5_file.attrs[key] = value