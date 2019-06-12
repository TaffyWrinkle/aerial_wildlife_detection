'''
    Helper function that imports YOLO labels into the database.
    Needs to be run on the file server.
    This assumes that the images of the dataset have already been placed in the
    folder of the connected file server (parameter "staticfiles_dir" in section [FileServer]
    of .ini file), and that the labels provided here match with a simple file directory lookup.

    Inputs:
    - labelFolder: path string for a directory with label files (see conventions below)

    Conventions:
    - Labels must be organized as text files in the "labelFolder", with one text file associated
      to exactly one image file.
    - Image-to-label file association: <file server staticfiles_dir>/<img_name>.jpg corresponds to
      <labelFolder>/<img_name>.txt
    - Label text files contain bounding boxes in YOLO format:
                
            <class index> <x> <y> <width> <height>\n
      with:
        - class index: the number of the class, specified in a file "classes.txt" in the same directory.
          One class name per line; class index is provided implicitly as the line number, starting at zero.
        - x, y: center coordinates of the bounding box, normalized to image width, resp. height
        - width, height: width and height of the bounding box, normalized to image width, resp. height
    - Images without a ground truth simply do not need an associated label text file.

    The script then proceeds by parsing the text files and scaling the coordinates back to absolute values,
    which is what will be stored in the database.
    Labels are stored in the "ANNOTATIONS" table, with the following non-standard field
    values:
        - timeCreated: (timestamp of the launch of this script)
        - timeRequired: -1
        - TODO: user
    Also adds class definitions.

    2019 Benjamin Kellenberger
'''

import os
import glob
from tqdm import tqdm
import datetime
import argparse
from PIL import Image
from util.configDef import Config
from modules import Database



if __name__ == '__main__':

    parser = argparse.ArgumentParser(description='Parse YOLO annotations and import into database.')
    parser.add_argument('--labelFolder', type=str, default='/datadrive/aerialelephants/dataset/bkellenb/labels', const=1, nargs='?',
                    help='Directory (absolute path) on this machine that contains the YOLO label text files.')
    parser.add_argument('--skipMismatches', type=bool, default=False, const=1, nargs='?',
                    help='Ignore label files without a corresponding image (default: False).')
    args = parser.parse_args()


    # setup
    if not args.labelFolder.endswith('/'):
        args.labelFolder += '/'

    currentDT = datetime.datetime.now()
    currentDT = '{}-{}-{} {}:{}:{}'.format(currentDT.year, currentDT.month, currentDT.day, currentDT.hour, currentDT.minute, currentDT.second)

    config = Config()
    dbConn = Database(config)
    if dbConn.conn is None:
        raise Exception('Error connecting to database.')
    dbSchema = config.getProperty('Database', 'schema')
    

    # check if running on file server
    imgBaseDir = config.getProperty('FileServer', 'staticfiles_dir')
    if not os.path.isdir(imgBaseDir):
        raise Exception('"{}" is not a valid directory on this machine. Are you running the script from the file server?'.format(imgBaseDir))

    if not os.path.isdir(args.labelFolder):
        raise Exception('"{}" is not a valid directory on this machine.'.format(args.labelFolder))


    # parse class names and indices
    classdef = {}
    with open(os.path.join(args.labelFolder, 'classes.txt'),'r') as f:
        lines = f.readlines()
    for idx, line in enumerate(lines):
        className = line.strip()

        # push to database
        dbConn.execute('''
            INSERT INTO {}.LABELCLASS (name)
            VALUES (
                %s
            )
        '''.format(dbSchema),
        (className,))

        # get newly assigned index
        returnVal = dbConn.execute('''
            SELECT id FROM {}.LABELCLASS WHERE name LIKE %s'''.format(dbSchema),
        (className+'%',),
        1)
        classdef[idx] = returnVal[0][0]



    # locate all images and their base names
    imgs = {}
    imgFiles = os.listdir(imgBaseDir)
    for i in imgFiles:
        tokens = i.split('.')
        baseName = i.replace('.' + tokens[-1],'')
        imgs[baseName] = i

        # push image to database
        dbConn.execute('''
            INSERT INTO {}.IMAGE (filename)
            VALUES (%s)
        '''.format(dbSchema),
        (i,))

    
    # locate all label files
    labelFiles = glob.glob(os.path.join(args.labelFolder, '*.txt'))

    for l in tqdm(labelFiles):

        if 'classes.txt' in l:
            continue

        l = l.replace(args.labelFolder, '')
        tokens = l.split('.')
        baseName = l.replace('.' + tokens[-1],'')

        # load matching image
        if not baseName in imgs:
            if args.skipMismatches:
                continue
            else:
                raise ValueError('Label file {} has no associated image'.format(l))
        imgPath = os.path.join(imgBaseDir, imgs[baseName])
        img = Image.open(imgPath)
        sz = img.size

        # load labels
        labelPath = os.path.join(args.labelFolder, l)
        with open(labelPath, 'r') as f:
            lines = f.readlines()

        # convert labels
        labels = []
        bboxes = []
        if len(lines):
            for line in lines:
                tokens = line.strip().split(' ')
                label = int(tokens[0])
                labels.append(label)
                bbox = [float(t) for t in tokens[1:]]
                bbox[0] *= sz[0]
                bbox[1] *= sz[1]
                bbox[2] *= sz[0]
                bbox[3] *= sz[1]
                bboxes.append(bbox)
            
                # push to database
                dbConn.execute('''
                    INSERT INTO {}.ANNOTATION (image, timeCreated, timeRequired, labelclass, x, y, width, height)
                    VALUES(
                        (SELECT id FROM {}.IMAGE WHERE filename LIKE %s),
                        (TIMESTAMP %s),
                        -1,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s
                    )
                '''.format(dbSchema, dbSchema),
                (baseName+'%', currentDT, classdef[label], bbox[0], bbox[1], bbox[2], bbox[3]))